#!/usr/bin/env python3
"""Run a live Home Assistant frontend smoke test with Playwright and Chrome."""

from __future__ import annotations

import json
import os
import re
import shutil
# This script only uses argv lists assembled by this file.
import subprocess  # nosec B404
import sys
import tempfile
import textwrap
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


PLAYWRIGHT_VERSION = "1.60.0"
DEFAULT_HA_AUTH_CLIENT_ID = "http://localhost/"
MIN_EXACT_REDACTION_LENGTH = 4
SENSITIVE_ENV_NAMES = (
    "HA_SMOKE_URL",
    "HA_TEST_URL",
    "HA_SMOKE_USER",
    "HA_TEST_USER",
    "HA_SMOKE_PASSWORD",
    "HA_TEST_PASSWORD",
    "HA_SMOKE_API_TOKEN",
    "HA_SMOKE_LONG_LIVED_TOKEN",
    "HA_LONG_LIVED_TOKEN",
    "LONG_LIVED_TOKEN",
)
BEARER_RE = re.compile(r"(?i)(Authorization:\s*Bearer\s+)[^\s\"']+")
JSON_TOKEN_RE = re.compile(
    r'("(?:(?:access|refresh)_token|token)"\s*:\s*")[^"]+(")'
)
JSON_ID_VALUE_RE = re.compile(
    r'("(?:(?:target|snapshot)_?(?:id|key)|latest_snapshot_id|'
    r'oldest_snapshot_id|id)"\s*:\s*")[^"]+(")'
)
JSON_NAME_VALUE_RE = re.compile(
    r'("(?:(?:friendly|target|snapshot_target|latest_snapshot|oldest_snapshot)_name|'
    r'(?:latest_snapshot|oldest_snapshot)_description|name|description)"\s*:\s*)'
    r'"[^"]*"'
)
JSON_NAME_ARRAY_RE = re.compile(
    r'("snapshot_(?:names|descriptions)"\s*:\s*)\[[^\]]*\]'
)
TOKEN_QUERY_RE = re.compile(
    r"([?&](?:access_token|refresh_token|token|code|state)=)[^&#\s\"']+"
)
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
UNDERSCORE_IPV4_RE = re.compile(r"(?<!\d)\d{1,3}_\d{1,3}_\d{1,3}_\d{1,3}(?!\d)")
BRACKETED_IPV6_RE = re.compile(r"\[[0-9a-fA-F:.%]{2,}\]")
BARE_IPV6_RE = re.compile(
    r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}"
    r"(?:%[A-Za-z0-9_.-]+)?(?![\w:])"
)
MAC_RE = re.compile(r"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")
LOCAL_HOSTNAME_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:home\.arpa|local|lan|home|internal|private|corp)"
    r"(?::\d{1,5})?"
    r"(?![A-Za-z0-9_-])"
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
UUID_RE = re.compile(
    r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9a-fA-F])"
)
# Redaction sentinel, not a secret.
TOKEN_SENTINEL = "\0TOKEN\0"  # nosec B105
VALUE_SENTINEL = "\0VALUE\0"
IP_SENTINEL = "\0IP\0"
ID_SENTINEL = "\0ID\0"
HOST_SENTINEL = "\0HOST\0"
MAC_SENTINEL = "\0MAC\0"


SCRIPT = r"""
const { chromium } = require("playwright");
const fs = require("fs");

const INVENTORY_SUFFIX = "_snapshot_inventory";
const INVENTORY_CREATE_SUFFIX = "_create_snapshot";
const DEFAULT_DISCOVERY_MODE = "auto";
const DEFAULT_CONNECT_TIMEOUT_MS = 90000;
const DEFAULT_NAV_TIMEOUT_MS = 30000;
const DEFAULT_CHROME_ARGS = "--no-sandbox,--disable-dev-shm-usage";

function requiredEnv(...names) {
  for (const name of names) {
    const value = process.env[name];
    if (value) {
      return value;
    }
  }
  throw new Error(`Missing required environment variable: ${names.join(" or ")}`);
}

function optionalEnv(defaultValue, ...names) {
  for (const name of names) {
    const value = process.env[name];
    if (value) {
      return value;
    }
  }
  return defaultValue;
}

function optionalEntityEnv(defaultValue, ...names) {
  const value = optionalEnv(defaultValue, ...names);
  return value ? String(value) : value;
}

function normalizeUrl(value) {
  return String(value).trim().replace(/\/+$/, "");
}

function toSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeEntityId(value) {
  return String(value || "").trim().toLowerCase();
}

function chooseString(value, fallback) {
  return value ? normalizeEntityId(value) : fallback;
}

function parseBooleanEnv(name, defaultValue) {
  const value = optionalEnv(null, name);
  if (value === null) {
    return defaultValue;
  }
  return ["1", "true", "yes", "on", "y"].includes(String(value).toLowerCase());
}

function parseIntEnv(name, defaultValue) {
  const raw = optionalEnv(null, name);
  if (raw === null) {
    return defaultValue;
  }
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value) || value <= 0) {
    return defaultValue;
  }
  return value;
}

async function ensureElementFilled(locator, value) {
  if (!(await locator.count())) {
    return false;
  }
  await locator.first().click();
  await locator.first().fill(value, { timeout: DEFAULT_NAV_TIMEOUT_MS });
  return true;
}

async function waitForHassStates(page, timeoutMs) {
  try {
    await page.waitForFunction(
      () => {
        const app = document.querySelector("home-assistant");
        return (
          app &&
          app.hass &&
          app.hass.states &&
          Object.keys(app.hass.states).length > 0
        );
      },
      { timeout: timeoutMs },
    );
    return true;
  } catch {
    return false;
  }
}

function getSmokeApiToken() {
  return optionalEnv(
    "",
    "HA_SMOKE_API_TOKEN",
    "HA_SMOKE_LONG_LIVED_TOKEN",
    "HA_LONG_LIVED_TOKEN",
    "LONG_LIVED_TOKEN"
  );
}

function isExternalAuthUrl(url) {
  return String(url || "").includes("/auth/authorize");
}

async function collectApiTokenFromBrowser(page, baseUrl) {
  try {
    const token = await page.evaluate((url) => {
      const raw = window.localStorage.getItem("hassTokens");
      if (!raw) {
        return "";
      }
      const getTokenValue = (value) => {
        if (typeof value === "string" && value.trim()) {
          return value.trim();
        }
        if (typeof value === "object" && value !== null) {
          if (typeof value.access_token === "string" && value.access_token.trim()) {
            return value.access_token.trim();
          }
          if (typeof value.token === "string" && value.token.trim()) {
            return value.token.trim();
          }
        }
        return "";
      };
      try {
        const parsed = JSON.parse(raw);
        const directToken = getTokenValue(parsed);
        if (directToken) {
          return directToken;
        }
        const targets = [];
        if (typeof url === "string") {
          const trimmed = url.replace(/\/+$/, "");
          if (trimmed) {
            targets.push(trimmed);
            targets.push(`${trimmed}/`);
          }
          try {
            const parsedUrl = new URL(url);
            targets.push(parsedUrl.origin);
            targets.push(`${parsedUrl.origin}/`);
          } catch {
            // Ignore bad URL data
          }
        }
        const fallbackKeys = [
          "http://homeassistant.local:8123",
          "http://homeassistant.local:8123/",
        ];
        for (const key of fallbackKeys) {
          if (!targets.includes(key)) {
            targets.push(key);
          }
        }
        for (const key of targets) {
          const keyToken = getTokenValue(parsed[key]);
          if (keyToken) {
            return keyToken;
          }
        }
        return "";
      } catch {
        return "";
      }
    }, baseUrl);
    return token || "";
  } catch {
    return "";
  }
}

function collectStateMapFromPage(page) {
  return page.evaluate(() => {
    const hass = document.querySelector("home-assistant")?.hass;
    if (!hass || !hass.states) {
      return {};
    }
    const wanted = Object.keys(hass.states).filter((id) => id.includes("snapshot"));
    const states = {};
    for (const entityId of wanted) {
      const state = hass.states[entityId];
      const attributes = state?.attributes || {};
      states[entityId] = {
        state: state.state,
        attributes,
        friendly_name: attributes.friendly_name || "",
        snapshot_inventory_available: attributes.snapshot_inventory_available,
        snapshot_inventory_status: attributes.snapshot_inventory_status,
        snapshot_count_source: attributes.snapshot_count_source,
        returned_snapshot_count: attributes.returned_snapshot_count,
        inventory_total: attributes.inventory_total,
        inventory_limit: attributes.inventory_limit,
        inventory_truncated: attributes.inventory_truncated,
        recent_snapshot_count: attributes.recent_snapshot_count,
        target_key: attributes.target_key,
        target_name: attributes.target_name,
        target_type: attributes.target_type,
        snapshot_target_key: attributes.snapshot_target_key,
        snapshot_target_name: attributes.snapshot_target_name,
        snapshot_target_type: attributes.snapshot_target_type,
      };
    }
    return states;
  });
}

async function collectStateMapFromApi(page, baseUrl, timeoutMs, token) {
  const apiToken = token || getSmokeApiToken();
  if (!apiToken) {
    return null;
  }
  const endpoint = `${baseUrl}/api/states`;
  let response;
  try {
    response = await page.request.get(endpoint, {
      headers: { Authorization: `Bearer ${apiToken}` },
      timeout: timeoutMs,
      failOnStatusCode: false,
    });
  } catch (error) {
    throw new Error(`Failed to request ${endpoint}: ${error.message}`);
  }
  if (!response.ok()) {
    throw new Error(
      `HA API token request failed for ${endpoint} with status ${response.status()} ${response.statusText()}`
    );
  }

  const payload = await response.json();
  if (!Array.isArray(payload)) {
    throw new Error(`Unexpected /api/states payload type from ${endpoint}`);
  }
  const states = {};
  for (const raw of payload) {
    if (!raw || !raw.entity_id) {
      continue;
    }
    const entityId = normalizeEntityId(raw.entity_id);
    if (!entityId.includes("snapshot")) {
      continue;
    }
    const attributes = raw.attributes || {};
    states[entityId] = {
      state: raw.state,
      attributes,
      friendly_name: attributes.friendly_name || "",
      snapshot_inventory_available: attributes.snapshot_inventory_available,
      snapshot_inventory_status: attributes.snapshot_inventory_status,
      snapshot_count_source: attributes.snapshot_count_source,
      returned_snapshot_count: attributes.returned_snapshot_count,
      inventory_total: attributes.inventory_total,
      inventory_limit: attributes.inventory_limit,
      inventory_truncated: attributes.inventory_truncated,
      recent_snapshot_count: attributes.recent_snapshot_count,
      target_key: attributes.target_key,
      target_name: attributes.target_name,
      target_type: attributes.target_type,
      snapshot_target_key: attributes.snapshot_target_key,
      snapshot_target_name: attributes.snapshot_target_name,
      snapshot_target_type: attributes.snapshot_target_type,
    };
  }
  return states;
}

function assertInventory(
  result,
  label,
  entityId,
  expectedStatus,
  expectedSource,
  required = true
) {
  if (!required) {
    if (!entityId || !result.states[entityId]) {
      return;
    }
  } else if (!entityId) {
    throw new Error(`${label} inventory entity is not configured`);
  }

  const state = result.states[entityId];
  if (!state) {
    throw new Error(`${label} inventory entity is missing: ${entityId}`);
  }
  if (state.snapshot_inventory_status !== expectedStatus) {
    throw new Error(
      `${label} inventory status expected ${expectedStatus}, got ${state.snapshot_inventory_status}: `
      + JSON.stringify(state)
    );
  }
  if (state.snapshot_count_source !== expectedSource) {
    throw new Error(
      `${label} inventory source expected ${expectedSource}, got ${state.snapshot_count_source}: `
      + JSON.stringify(state)
    );
  }
}

function assertButton(result, label, entityId, expectedState, required = true) {
  if (!required) {
    if (!entityId || !result.states[entityId]) {
      return;
    }
  } else if (!entityId) {
    throw new Error(`${label} button entity is not configured`);
  }

  const state = result.states[entityId];
  if (!state) {
    if (expectedState === "missing") {
      return;
    }
    throw new Error(`${label} button is missing: ${entityId}`);
  }

  if (expectedState === "available") {
    if (state.state === "unavailable") {
      throw new Error(`${label} button expected available, got unavailable`);
    }
    return;
  }
  if (expectedState === "missing") {
    throw new Error(
      `${label} button expected to be missing, got ${state.state}: `
      + JSON.stringify(state)
    );
  }
  if (state.state !== expectedState) {
    throw new Error(
      `${label} button expected ${expectedState}, got ${state.state}: `
      + JSON.stringify(state)
    );
  }
}

function createButtonCandidates(inventoryEntityId, allStates) {
  const id = normalizeEntityId(inventoryEntityId);
  if (!id) {
    return [];
  }
  const candidates = [
    normalizeEntityId(
      id
        .replace(/^sensor\./, "button.")
        .replace(/_snapshot_inventory$/, INVENTORY_CREATE_SUFFIX)
    ),
  ];

  const stem = id.replace(/^sensor\./, "").replace(/_snapshot_inventory$/, "");
  const fallback = normalizeEntityId(`button.${stem}${INVENTORY_CREATE_SUFFIX}`);
  if (fallback !== candidates[0]) {
    candidates.push(fallback);
  }

  if (allStates) {
    for (const candidate of Object.keys(allStates)) {
      if (!candidate.startsWith("button.") || !candidate.includes("snapshot")) {
        continue;
      }
      const normalized = normalizeEntityId(candidate);
      const normalizedStem = normalized
        .replace(/^button\./, "")
        .replace(/_create_snapshot$/, "")
        .replace(/_snapshot$/, "");
      if (normalizedStem.includes(stem)) {
        candidates.push(normalized);
      }
    }
  }
  return [...new Set(candidates.filter(Boolean))];
}

function discoverTargets(states) {
  const discoveryMode = toSearchText(
    optionalEnv(DEFAULT_DISCOVERY_MODE, "HA_SMOKE_DISCOVERY_MODE")
  );
  if (discoveryMode === "off") {
    return {
      targets: [],
      okInventory: "",
      unsupportedInventory: "",
      okButton: "",
      unsupportedButton: "",
    };
  }

  const targetFilter = toSearchText(
    optionalEnv("", "HA_SMOKE_TARGET_FILTER", "HA_SMOKE_SNAPSHOT_TARGET_FILTER")
  );
  const entityPrefixFilter = toSearchText(
    optionalEnv(
      "",
      "HA_SMOKE_SNAPSHOT_ENTITY_PREFIX",
      "HA_SMOKE_SNAPSHOT_PREFIX"
    )
  );

  const inventories = Object.entries(states || {})
    .filter(([id]) => id.startsWith("sensor.") && id.includes(INVENTORY_SUFFIX))
    .map(([id, state]) => {
      const attrs = state?.attributes || {};
      return {
        id,
        status: toSearchText(attrs.snapshot_inventory_status || state.snapshot_inventory_status),
        source: String(attrs.snapshot_count_source || state.snapshot_count_source || ""),
        friendly_name: String(attrs.friendly_name || state.friendly_name || ""),
        target_key: String(attrs.target_key || attrs.snapshot_target_key || ""),
        target_name: String(attrs.target_name || attrs.snapshot_target_name || ""),
        target_type: String(attrs.target_type || ""),
      };
    })
    .filter((entry) => {
      if (!targetFilter && !entityPrefixFilter) {
        return true;
      }
      const haystack = toSearchText(
        `${entry.id} ${entry.friendly_name} ${entry.target_key} ${entry.target_type}`
      );
      return (
        (!targetFilter || haystack.includes(targetFilter)) &&
        (!entityPrefixFilter || haystack.includes(entityPrefixFilter))
      );
    });

  const okExplicit = optionalEntityEnv("", "HA_SMOKE_SNAPSHOT_OK_INVENTORY_ENTITY");
  const unsupportedExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_INVENTORY_ENTITY"
  );
  const okButtonExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_OK_BUTTON_ENTITY",
    "HA_SMOKE_OK_BUTTON_ENTITY",
    "HA_SMOKE_SNAPSHOT_OK_CREATE_BUTTON_ENTITY"
  );
  const unsupportedButtonExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_UNAVAILABLE_BUTTON_ENTITY",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_BUTTON_ENTITY",
    "HA_SMOKE_UNSUPPORTED_BUTTON_ENTITY"
  );

  const okFromDiscovery = inventories.find((entry) => entry.status === "ok")
    || inventories[0]
    || { id: "" };
  const unsupportedFromDiscovery = inventories.find(
    (entry) => entry.status === "unsupported"
  ) || { id: "" };

  const okInventory = chooseString(okExplicit, okFromDiscovery.id);
  const unsupportedInventory = chooseString(
    unsupportedExplicit,
    unsupportedFromDiscovery.id
  );

  const okButtonCandidates = createButtonCandidates(okInventory, states);
  const unsupportedButtonCandidates = createButtonCandidates(
    unsupportedInventory,
    states
  );
  const okButton = chooseString(
    okButtonExplicit,
    okButtonCandidates.find((id) => id && states[id]) || okButtonCandidates[0] || ""
  );
  const unsupportedButton = chooseString(
    unsupportedButtonExplicit,
    unsupportedButtonCandidates.find((id) => id && states[id]) ||
      unsupportedButtonCandidates[0] ||
      ""
  );

  return {
    targets: inventories,
    okInventory,
    unsupportedInventory,
    okButton,
    unsupportedButton,
  };
}

async function main() {
  const base = normalizeUrl(requiredEnv("HA_SMOKE_URL", "HA_TEST_URL"));
  const chrome = requiredEnv("HA_SMOKE_CHROME", "HA_TEST_CHROME");
  const requireUnsupported = parseBooleanEnv("HA_SMOKE_REQUIRE_UNSUPPORTED", false);
  const headless = parseBooleanEnv("HA_SMOKE_HEADLESS", true);
  const skipLogin =
    parseBooleanEnv("HA_SMOKE_SKIP_LOGIN", false) ||
    parseBooleanEnv("HA_SMOKE_AUTH_SKIP", false);
  const username = skipLogin ? "" : requiredEnv("HA_SMOKE_USER", "HA_TEST_USER");
  const password = skipLogin ? "" : requiredEnv("HA_SMOKE_PASSWORD", "HA_TEST_PASSWORD");
  const connectTimeoutMs = parseIntEnv(
    "HA_SMOKE_CONNECT_TIMEOUT_MS",
    DEFAULT_CONNECT_TIMEOUT_MS
  );
  const navTimeoutMs = parseIntEnv("HA_SMOKE_NAV_TIMEOUT_MS", DEFAULT_NAV_TIMEOUT_MS);
  const screenshotsDir = optionalEnv("", "HA_SMOKE_SCREENSHOTS_DIR", "HA_SMOKE_SCREENSHOT_DIR");
  const chromeUserDataDir = optionalEnv("", "HA_SMOKE_CHROME_USER_DATA_DIR");
  const chromeArgs = optionalEnv(DEFAULT_CHROME_ARGS, "HA_SMOKE_CHROME_ARGS");

  const okInventoryExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_OK_INVENTORY_ENTITY"
  );
  const unsupportedInventoryExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_INVENTORY_ENTITY"
  );
  const okButtonExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_OK_BUTTON_ENTITY",
    "HA_SMOKE_OK_BUTTON_ENTITY",
    "HA_SMOKE_SNAPSHOT_OK_CREATE_BUTTON_ENTITY"
  );
  const unsupportedButtonExplicit = optionalEntityEnv(
    "",
    "HA_SMOKE_SNAPSHOT_UNAVAILABLE_BUTTON_ENTITY",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_BUTTON_ENTITY",
    "HA_SMOKE_UNSUPPORTED_BUTTON_ENTITY"
  );

  const okInventoryStatus = optionalEnv(
    "ok",
    "HA_SMOKE_SNAPSHOT_OK_INVENTORY_STATUS"
  );
  const okInventorySource = optionalEnv(
    "inventory_total",
    "HA_SMOKE_SNAPSHOT_OK_INVENTORY_SOURCE"
  );
  const unsupportedInventoryStatus = optionalEnv(
    "unsupported",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_INVENTORY_STATUS"
  );
  const unsupportedInventorySource = optionalEnv(
    "snapshot_settings_total_count",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_INVENTORY_SOURCE"
  );
  const okButtonExpectedState = optionalEnv(
    "available",
    "HA_SMOKE_SNAPSHOT_OK_BUTTON_STATE"
  );
  const unsupportedButtonExpectedState = optionalEnv(
    "missing",
    "HA_SMOKE_SNAPSHOT_UNSUPPORTED_BUTTON_STATE",
    "HA_SMOKE_UNSUPPORTED_BUTTON_STATE"
  );

  const parsedChromeArgs = String(chromeArgs).split(",").map((value) => value.trim())
    .filter(Boolean);
  const browser = chromeUserDataDir
    ? null
    : await chromium.launch({
      headless,
      executablePath: chrome,
      args: parsedChromeArgs,
    });
  const context = chromeUserDataDir
    ? await chromium.launchPersistentContext(chromeUserDataDir, {
      headless,
      executablePath: chrome,
      args: parsedChromeArgs,
      viewport: { width: 1440, height: 1000 },
    })
    : await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
  const page = await context.newPage();

  try {
    page.on("console", (msg) => {
      const text = msg.text();
      if (/unifi|error|failed|exception/i.test(text)) {
        console.log(`browser_console: ${msg.type()} ${text.slice(0, 300)}`);
      }
    });

    await page.goto(`${base}/`, {
      waitUntil: "domcontentloaded",
      timeout: navTimeoutMs,
    });

    const authFlow = page.locator("ha-auth-flow");
    if (await authFlow.count()) {
      if (skipLogin) {
        console.log(
          "INFO: Login is present but HA_SMOKE_SKIP_LOGIN/HA_SMOKE_AUTH_SKIP=true, skipping interactive sign-in"
        );
      } else {
        const usernameField = page.getByRole("textbox", { name: /user|benutzer|username/i });
        const passwordField = page.getByRole("textbox", { name: /password|kennwort|passwort/i });
        const fallbackUsername = page.locator('ha-input[type="text"] input').first();
        const fallbackPassword = page.locator('ha-input[type="password"] input').first();
        const loginButton = page
          .getByRole("button", { name: /log in|anmelden|sign in/i })
          .first();
        const alternateLoginButton = page.locator("ha-auth-flow form ha-button").first();

        const usernameFilled = await ensureElementFilled(usernameField, username);
        if (!usernameFilled && !(await ensureElementFilled(fallbackUsername, username))) {
          throw new Error("Login form username field could not be located");
        }
        const passwordFilled = await ensureElementFilled(passwordField, password);
        if (!passwordFilled && !(await ensureElementFilled(fallbackPassword, password))) {
          throw new Error("Login form password field could not be located");
        }

        if (await loginButton.count()) {
          await loginButton.click();
        } else if (await alternateLoginButton.count()) {
          await alternateLoginButton.click();
        } else {
          throw new Error(
            "Login form detected, but no login button could be found"
          );
        }

        await page.waitForFunction(
          () => {
            return !document.querySelector("ha-auth-flow");
          },
          { timeout: navTimeoutMs }
        );
        const authStillVisible = await page.locator("ha-auth-flow").count();
        if (authStillVisible) {
          throw new Error("Login was submitted but auth flow is still visible");
        }
      }
    }

    const connected = await waitForHassStates(page, connectTimeoutMs);
    const apiTokenFromEnv = getSmokeApiToken();
    const apiTokenFromBrowser = apiTokenFromEnv
      ? ""
      : await collectApiTokenFromBrowser(page, base);
    const apiToken = apiTokenFromEnv || apiTokenFromBrowser;
    if (apiTokenFromBrowser) {
      console.log("INFO: Using HA API token from browser localStorage.");
    }
    let stateMap = null;
    let usedApiFallback = false;
    if (!connected) {
      const stillAuthFlow = await authFlow.count();
      const currentUrl = page.url();
      const debugState = await page.evaluate(() => {
        const app = document.querySelector("home-assistant");
        return {
          hasHomeAssistant: !!app,
          hasHass: !!(app && app.hass),
          stateCount: app && app.hass && app.hass.states ? Object.keys(app.hass.states).length : 0,
          title: document.title,
          pathname: location.pathname,
        };
      });
      const isExternalAuth =
        isExternalAuthUrl(currentUrl) || isExternalAuthUrl(debugState.pathname);
      const shouldTryApiFallback = Boolean(apiToken);
      const oauthHint =
        isExternalAuth
          ? "HA appears to be using an external OAuth/authorization flow."
          : "";
      if (shouldTryApiFallback) {
        console.log(
          "WARN: Connected state was not reached, attempting API token fallback via /api/states"
        );
        try {
          const apiStates = await collectStateMapFromApi(
            page,
            base,
            connectTimeoutMs,
            apiToken
          );
          if (apiStates && Object.keys(apiStates).length) {
            stateMap = apiStates;
            usedApiFallback = true;
            console.log(
              `INFO: Loaded Home Assistant states via ${apiTokenFromEnv ? "HA_SMOKE_API_TOKEN" : "browser token"}`
            );
          } else {
            console.log("WARN: /api/states did not return snapshot states");
          }
        } catch (error) {
          console.log(`WARN: API fallback failed: ${error.message}`);
        }
      }

      if (stateMap) {
        console.log("INFO: Proceeding using API state snapshot");
      } else {
        if (screenshotsDir) {
          await fs.promises.mkdir(screenshotsDir, { recursive: true });
          await page.screenshot({
            path: `${screenshotsDir}/ha-smoke-auth-timeout-${Date.now()}.png`,
            fullPage: true,
          });
        }
        if (stillAuthFlow) {
          const tokenHint =
            apiToken
              ? ""
              : " Set HA_SMOKE_API_TOKEN (long-lived token) when using external OAuth with skip-login, "
              + "or run once with HA_SMOKE_CHROME_USER_DATA_DIR logged in.";
          throw new Error(
            `Home Assistant did not reach connected state. Likely login failed or auth is still blocked.`
            + ` title=${debugState.title} url=${currentUrl}. ${oauthHint}${tokenHint}`
          );
        }
        if (apiToken) {
          throw new Error(
            `Home Assistant did not reach connected state after API fallback.`
            + ` title=${debugState.title} url=${currentUrl}.`
          );
        }
        throw new Error(
          `Home Assistant did not reach connected state in ${connectTimeoutMs}ms.`
          + ` title=${debugState.title} url=${currentUrl}. ${oauthHint}`
          + ` Set HA_SMOKE_API_TOKEN (long-lived token) when using external OAuth with skip-login, `
          + `or run once with HA_SMOKE_CHROME_USER_DATA_DIR logged in.`
        );
      }
    }

    if (!stateMap) {
      stateMap = await collectStateMapFromPage(page);
    }

    if (!stateMap || !Object.keys(stateMap).length) {
      throw new Error("No snapshot related states found in Home Assistant");
    }

    const discovered = discoverTargets(stateMap);
    const resolvedOkInventory = chooseString(
      okInventoryExplicit,
      discovered.okInventory
    );
    const resolvedUnsupportedInventory = chooseString(
      unsupportedInventoryExplicit,
      discovered.unsupportedInventory
    );
    const resolvedOkButton = chooseString(
      okButtonExplicit,
      discovered.okButton
    );
    const resolvedUnsupportedButton = chooseString(
      unsupportedButtonExplicit,
      discovered.unsupportedButton
    );

    if (discovered.targets.length > 0) {
      console.log(
        JSON.stringify(
          {
            discovery_mode: optionalEnv(
              DEFAULT_DISCOVERY_MODE,
              "HA_SMOKE_DISCOVERY_MODE"
            ),
            discovered_targets: discovered.targets.map((entry) => ({
              id: entry.id,
              status: entry.status,
              source: entry.source,
              target_key: entry.target_key,
              target_type: entry.target_type,
            })),
            selected: {
              ok_inventory: resolvedOkInventory,
              unsupported_inventory: resolvedUnsupportedInventory,
              ok_button: resolvedOkButton,
              unsupported_button: resolvedUnsupportedButton,
            },
          },
          null,
          2
        )
      );
    }

    const checkUnsupported = Boolean(
      resolvedUnsupportedInventory || resolvedUnsupportedButton || requireUnsupported
    );
    const shouldCheckUnsupported = Boolean(
      checkUnsupported &&
      (resolvedUnsupportedInventory || resolvedUnsupportedButton)
    );

    const entityIds = [
      resolvedOkInventory,
      resolvedUnsupportedInventory,
      resolvedOkButton,
      resolvedUnsupportedButton,
    ].filter(Boolean);
    const uniqueEntityIds = [...new Set(entityIds)];

    let result;
    if (usedApiFallback) {
      const selected = {};
      for (const entityId of uniqueEntityIds) {
        selected[entityId] = stateMap[entityId] ? { ...stateMap[entityId] } : null;
      }
      result = {
        url: page.url(),
        title: await page.title(),
        connected: true,
        language: undefined,
        state_count: Object.keys(stateMap).length,
        states: selected,
      };
    } else {
      result = await page.evaluate(({ ids, allStates }) => {
        const selected = {};
        for (const entityId of ids) {
          selected[entityId] = allStates[entityId] ? { ...allStates[entityId] } : null;
        }
        const app = document.querySelector("home-assistant");
        return {
          url: location.href,
          title: document.title,
          connected: !!(app && app.hass && app.hass.states),
          language: app ? app.hass?.language : undefined,
          state_count: Object.keys(allStates).length,
          states: selected,
        };
      }, { ids: uniqueEntityIds, allStates: stateMap });
    }

    if (!result.connected) {
      throw new Error("Home Assistant frontend is not connected");
    }

    if (!resolvedOkInventory) {
      throw new Error("No supported snapshot inventory target selected");
    }

    assertInventory(
      result,
      "supported snapshot target",
      resolvedOkInventory,
      okInventoryStatus,
      okInventorySource
    );
    assertButton(
      result,
      "supported snapshot target",
      resolvedOkButton,
      okButtonExpectedState
    );

    if (shouldCheckUnsupported) {
      assertInventory(
        result,
        "unsupported snapshot target",
        resolvedUnsupportedInventory,
        unsupportedInventoryStatus,
        unsupportedInventorySource,
        Boolean(resolvedUnsupportedInventory)
      );
      assertButton(
        result,
        "unsupported snapshot target",
        resolvedUnsupportedButton,
        unsupportedButtonExpectedState,
        Boolean(resolvedUnsupportedButton)
      );
    } else if (requireUnsupported) {
      throw new Error(
        "HA_SMOKE_REQUIRE_UNSUPPORTED is enabled, but no unsupported snapshot inventory/button was found"
      );
    } else {
      console.log(
        "INFO: No unsupported snapshot target configured or discovered; skipping unsupported checks"
      );
    }

    console.log(JSON.stringify(result, null, 2));
  } finally {
    await context.close();
    if (browser) {
      await browser.close();
    }
  }
}

main().catch((err) => {
  console.error(err.stack || err.message || String(err));
  process.exit(1);
});
"""


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def _find_chrome() -> str:
    configured = _env("HA_SMOKE_CHROME", "HA_TEST_CHROME")
    if configured:
        path = Path(configured)
        if path.exists():
            return str(path)
        _fail(f"Configured Chrome executable does not exist: {configured}")

    for binary in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(binary)
        if found:
            return found

    _fail("Chrome or Chromium is required; set HA_SMOKE_CHROME to the executable path")


def _require_tools() -> None:
    for tool in ("node", "npm"):
        if not shutil.which(tool):
            _fail(f"{tool} is required to run the frontend smoke test")


def _require_env() -> None:
    skip_login = _env("HA_SMOKE_SKIP_LOGIN", "HA_SMOKE_AUTH_SKIP")
    skip_login_enabled = False
    if skip_login is not None:
        skip_login_enabled = str(skip_login).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "y",
        }

    required = {
        "HA_SMOKE_URL or HA_TEST_URL": _env("HA_SMOKE_URL", "HA_TEST_URL"),
    }
    if not skip_login_enabled:
        required["HA_SMOKE_USER or HA_TEST_USER"] = _env("HA_SMOKE_USER", "HA_TEST_USER")
        required["HA_SMOKE_PASSWORD or HA_TEST_PASSWORD"] = _env(
            "HA_SMOKE_PASSWORD",
            "HA_TEST_PASSWORD",
        )
    missing = [name for name, value in required.items() if not value]
    if missing:
        details = "\n".join(f"  - {name}" for name in missing)
        _fail(f"Missing required environment variables:\n{details}")


def _has_smoke_api_token() -> bool:
    return bool(
        _env(
            "HA_SMOKE_API_TOKEN",
            "HA_SMOKE_LONG_LIVED_TOKEN",
            "HA_LONG_LIVED_TOKEN",
            "LONG_LIVED_TOKEN",
        )
    )


def _auth_flow_token_enabled() -> bool:
    return _env_bool("HA_SMOKE_AUTH_FLOW_TOKEN", True)


def _request_url(base_url: str, path: str) -> str:
    """Build a Home Assistant auth URL after enforcing http(s)."""
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("HA smoke URL must be an http(s) URL")
    if not path.startswith("/"):
        raise RuntimeError("HA smoke request path must be absolute")
    return base_url.rstrip("/") + path


def _request_json(
    base_url: str,
    path: str,
    payload: dict[str, object] | None,
    *,
    timeout: float = 20.0,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        _request_url(base_url, path),
        data=data,
        headers={"Content-Type": "application/json"},
    )
    # _request_url enforces http(s) and absolute local API paths.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        body = response.read().decode()
        result = json.loads(body) if body else {}
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected JSON response from {path}")
        return result


def _request_form(
    base_url: str,
    path: str,
    payload: dict[str, str],
    *,
    timeout: float = 20.0,
) -> dict[str, object]:
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(
        _request_url(base_url, path),
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # _request_url enforces http(s) and absolute local API paths.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        body = response.read().decode()
        result = json.loads(body) if body else {}
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected form response from {path}")
        return result


def _login_ha_auth_flow(
    base_url: str,
    username: str,
    password: str,
    *,
    client_id: str = DEFAULT_HA_AUTH_CLIENT_ID,
    timeout: float = 20.0,
) -> tuple[str, str | None]:
    flow = _request_json(
        base_url,
        "/auth/login_flow",
        {
            "client_id": client_id,
            "handler": ["homeassistant", None],
            "redirect_uri": client_id,
        },
        timeout=timeout,
    )
    flow_id = flow.get("flow_id")
    if not isinstance(flow_id, str) or not flow_id:
        raise RuntimeError("HA auth-flow did not return a flow_id")

    login = _request_json(
        base_url,
        f"/auth/login_flow/{flow_id}",
        {
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        timeout=timeout,
    )
    if login.get("type") != "create_entry":
        raise RuntimeError(
            "HA auth-flow did not create an entry: "
            f"type={login.get('type')} errors={login.get('errors')}"
        )
    code = login.get("result")
    if not isinstance(code, str) or not code:
        raise RuntimeError("HA auth-flow did not return an authorization code")

    token = _request_form(
        base_url,
        "/auth/token",
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
        },
        timeout=timeout,
    )
    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("HA auth-flow token response did not include access_token")
    if not isinstance(refresh_token, str):
        refresh_token = None
    return access_token, refresh_token


def _revoke_ha_refresh_token(
    base_url: str,
    refresh_token: str,
) -> bool:
    try:
        _request_form(
            base_url,
            "/auth/token",
            {
                "token": refresh_token,
                "action": "revoke",
            },
            timeout=10,
        )
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")[:120]
        try:
            body = _redact_smoke_output(
                body,
                sensitive_values=(refresh_token,),
            ).strip()
        finally:
            err.close()
        print(
            "[WARN] HA refresh token revoke failed: "
            f"HTTP {err.code} {body}",
            file=sys.stderr,
        )
        return False
    except (OSError, TimeoutError, urllib.error.URLError) as err:
        details = _redact_smoke_output(
            f"{type(err).__name__}: {err}",
            sensitive_values=(base_url, refresh_token),
        ).strip()
        print(
            f"[WARN] HA refresh token revoke failed: {details}",
            file=sys.stderr,
        )
        return False
    return True


def _redact_smoke_output(
    text: str,
    sensitive_values: tuple[str, ...] = (),
) -> str:
    """Redact secrets and host details before printing smoke subprocess output."""
    redacted = text

    redacted = _redact_structured_smoke_values(redacted)
    exact_values: list[tuple[str, str]] = []
    short_values: list[tuple[str, str]] = []
    for name in SENSITIVE_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            label = f"<redacted:{name.lower()}>"
            if len(value) >= MIN_EXACT_REDACTION_LENGTH:
                exact_values.append((value, label))
            else:
                short_values.append((value, label))
    for value in sensitive_values:
        if value:
            if len(value) >= MIN_EXACT_REDACTION_LENGTH:
                exact_values.append((value, "<redacted>"))
            else:
                short_values.append((value, "<redacted>"))
    exact_sentinels: list[tuple[str, str]] = []
    for index, (value, label) in enumerate(
        sorted(exact_values, key=lambda item: len(item[0]), reverse=True)
    ):
        sentinel = f"\0ENV{index}\0"
        redacted = redacted.replace(value, sentinel)
        exact_sentinels.append((sentinel, label))
    for index, (value, label) in enumerate(
        sorted(short_values, key=lambda item: len(item[0]), reverse=True)
    ):
        sentinel = f"\0SHORT{index}\0"
        redacted = _replace_bounded_sensitive_value(redacted, value, sentinel)
        exact_sentinels.append((sentinel, label))

    # Repeat structural redaction for values that were not exact env matches.
    redacted = _redact_structured_smoke_values(redacted)
    for sentinel, label in exact_sentinels:
        redacted = redacted.replace(sentinel, label)
    return (
        redacted.replace(TOKEN_SENTINEL, "<redacted-token>")
        .replace(VALUE_SENTINEL, "<redacted>")
        .replace(IP_SENTINEL, "<redacted-ip>")
        .replace(ID_SENTINEL, "<redacted-id>")
        .replace(HOST_SENTINEL, "<redacted-host>")
        .replace(MAC_SENTINEL, "<redacted-mac>")
    )


def _replace_bounded_sensitive_value(text: str, value: str, replacement: str) -> str:
    """Replace short sensitive values only when they appear as standalone tokens."""
    pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])")
    return pattern.sub(replacement, text)


def _redact_structured_smoke_values(text: str) -> str:
    """Replace structured secret-like values with internal sentinels."""
    redacted = BEARER_RE.sub(rf"\1{TOKEN_SENTINEL}", text)
    redacted = JSON_TOKEN_RE.sub(rf"\1{TOKEN_SENTINEL}\2", redacted)
    redacted = JSON_ID_VALUE_RE.sub(rf"\1{ID_SENTINEL}\2", redacted)
    redacted = JSON_NAME_VALUE_RE.sub(rf'\1"{VALUE_SENTINEL}"', redacted)
    redacted = JSON_NAME_ARRAY_RE.sub(rf'\1["{VALUE_SENTINEL}"]', redacted)
    redacted = TOKEN_QUERY_RE.sub(rf"\1{VALUE_SENTINEL}", redacted)
    redacted = JWT_RE.sub(TOKEN_SENTINEL, redacted)
    redacted = UUID_RE.sub(ID_SENTINEL, redacted)
    redacted = MAC_RE.sub(MAC_SENTINEL, redacted)
    redacted = BRACKETED_IPV6_RE.sub(IP_SENTINEL, redacted)
    redacted = BARE_IPV6_RE.sub(IP_SENTINEL, redacted)
    redacted = LOCAL_HOSTNAME_RE.sub(HOST_SENTINEL, redacted)
    redacted = IPV4_RE.sub(IP_SENTINEL, redacted)
    return UNDERSCORE_IPV4_RE.sub(IP_SENTINEL, redacted)


def _write_redacted_output(
    stream: object,
    text: str,
    *,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    """Write sanitized subprocess output to a text stream."""
    if not text:
        return
    stream.write(_redact_smoke_output(text, sensitive_values=sensitive_values))
    stream.flush()


def _run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    quiet: bool = False,
) -> None:
    # Command argv is assembled by this script from fixed command names.
    proc = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    child_sensitive_values: list[str] = []
    if env:
        for name in SENSITIVE_ENV_NAMES:
            value = env.get(name)
            if value:
                child_sensitive_values.append(value)
    if not quiet:
        _write_redacted_output(
            sys.stdout,
            proc.stdout,
            sensitive_values=tuple(child_sensitive_values),
        )
    _write_redacted_output(
        sys.stderr,
        proc.stderr,
        sensitive_values=tuple(child_sensitive_values),
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    """Install a temporary Playwright package and run the live smoke test."""
    _require_tools()
    _require_env()
    chrome = _find_chrome()
    base_url = _env("HA_SMOKE_URL", "HA_TEST_URL")
    if base_url is None:
        _fail("Missing required environment variable: HA_SMOKE_URL or HA_TEST_URL")
    base_url = _request_url(base_url, "/").rstrip("/")
    auth_flow_access_token: str | None = None
    auth_flow_refresh_token: str | None = None

    playwright_version = _env(
        "HA_SMOKE_PLAYWRIGHT_VERSION",
        default=PLAYWRIGHT_VERSION,
    )
    if playwright_version is None:
        _fail("Missing Playwright version")

    if _auth_flow_token_enabled() and not _has_smoke_api_token():
        username = _env("HA_SMOKE_USER", "HA_TEST_USER")
        password = _env("HA_SMOKE_PASSWORD", "HA_TEST_PASSWORD")
        if username and password:
            try:
                auth_flow_access_token, auth_flow_refresh_token = _login_ha_auth_flow(
                    base_url,
                    username,
                    password,
                )
                print("[OK] HA auth-flow API token created for smoke fallback", flush=True)
            except (
                RuntimeError,
                TimeoutError,
                OSError,
                urllib.error.URLError,
                json.JSONDecodeError,
            ) as err:
                details = _redact_smoke_output(
                    f"{type(err).__name__}: {err}",
                    sensitive_values=(base_url, username, password),
                ).strip()
                print(
                    "[WARN] HA auth-flow API token creation failed; "
                    "falling back to browser login: "
                    f"{details}",
                    file=sys.stderr,
                )

    with tempfile.TemporaryDirectory(prefix="ha-unifi-unas-smoke-") as tmp:
        tmp_path = Path(tmp)
        _run(["npm", "init", "-y"], tmp_path, quiet=True)
        npm_env = os.environ.copy()
        npm_env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
        _run(
            [
                "npm",
                "install",
                "--no-save",
                "--silent",
                f"playwright@{playwright_version}",
            ],
            tmp_path,
            env=npm_env,
        )

        script_path = tmp_path / "smoke.js"
        script_path.write_text(textwrap.dedent(SCRIPT).strip() + "\n", encoding="utf-8")

        run_env = os.environ.copy()
        run_env["HA_SMOKE_CHROME"] = chrome
        if auth_flow_access_token:
            run_env["HA_SMOKE_API_TOKEN"] = auth_flow_access_token
            run_env["HA_SMOKE_SKIP_LOGIN"] = "true"
        try:
            _run(["node", str(script_path)], tmp_path, env=run_env)
        finally:
            if (
                auth_flow_refresh_token
                and _revoke_ha_refresh_token(base_url, auth_flow_refresh_token)
            ):
                print("[OK] HA refresh token revoked")


if __name__ == "__main__":
    main()
