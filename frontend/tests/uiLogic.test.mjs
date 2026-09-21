import assert from "node:assert/strict";
import test from "node:test";

import { shouldClearForm, submissionNotice, terminalStatuses, timelineText } from "../src/uiLogic.ts";

const snapshot = {
  text: "request",
  key: "key",
  workflow: "summarize_text",
  scenario: "normal",
};

test("new submissions and idempotent replays have distinct feedback", () => {
  assert.equal(submissionNotice(false, "12345678-abcd"), "Job queued: 12345678");
  const replay = submissionNotice(true, "12345678-abcd");
  assert.equal(replay, "Existing execution reused — no new job was created. (12345678)");
  assert.doesNotMatch(replay, /Job queued/);
});

test("terminal clearing requires the unchanged submitted form", () => {
  assert.equal(terminalStatuses.has("queued"), false);
  assert.equal(terminalStatuses.has("completed"), true);
  assert.equal(shouldClearForm(snapshot, snapshot, "completed"), true);
  assert.equal(shouldClearForm(snapshot, { ...snapshot, text: "new draft" }, "completed"), false);
  assert.equal(shouldClearForm(snapshot, snapshot, "running"), false);
});

test("retry delay appears only on the retry scheduled event", () => {
  const context = {
    retry_delay_seconds: 5,
    error: { code: "ProviderRateLimited", message: "Provider rate limit reached." },
  };
  const failure = timelineText({ id: 1, level: "warning", created_at: "", context,
    message: "Retryable transient failure" });
  const scheduled = timelineText({ id: 2, level: "info", created_at: "", context,
    message: "Retry scheduled" });
  assert.equal(failure, "Retryable transient failure · ProviderRateLimited: Provider rate limit reached.");
  assert.equal(scheduled, "Retry scheduled in 5s · ProviderRateLimited: Provider rate limit reached.");
  assert.doesNotMatch(failure, /failure in 5s/);
});
