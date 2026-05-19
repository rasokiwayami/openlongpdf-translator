(() => {
  function startAssist(config) {
    const server = config.server;
    const token = config.token;
    const panelId = "openlongpdf-assist-panel";
    let panel = document.getElementById(panelId);
    if (panel) {
      panel.remove();
      return;
    }

    panel = document.createElement("div");
    panel.id = panelId;
    panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#111827;color:#f9fafb;border:1px solid #4b5563;border-radius:8px;padding:12px;font:14px system-ui;box-shadow:0 8px 24px rgba(0,0,0,.25);max-width:340px";
    panel.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px">OpenLongPDF Assist</div>
      <button id="openlongpdf-send-next" style="margin:0 6px 6px 0;padding:6px 8px">Send next pack</button>
      <button id="openlongpdf-auto-send" style="margin:0 0 6px 0;padding:6px 8px">Auto translate all</button>
      <button id="openlongpdf-close" style="margin-left:6px;padding:6px 8px">Close</button>
      <div id="openlongpdf-status" style="margin-top:6px;color:#d1d5db">Ready.</div>
    `;
    document.body.appendChild(panel);

    const status = panel.querySelector("#openlongpdf-status");
    const setStatus = (text) => {
      status.textContent = text;
    };
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    async function fetchNextPack() {
      const response = await fetch(`${server}/assist/next.json?token=${encodeURIComponent(token)}`);
      if (!response.ok) throw new Error(`OpenLongPDF local server returned ${response.status}`);
      const data = await response.json();
      if (data.blocked) throw new Error(data.error || "OpenLongPDF is blocked by a failed pack. Retry it in the local GUI.");
      return data;
    }

    async function postLocal(path, payload) {
      const response = await fetch(`${server}${path}?token=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const text = await response.text();
      let data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (_error) {
          data = { error: text };
        }
      }
      if (!response.ok) throw new Error(data.error || `OpenLongPDF local server returned ${response.status}`);
      return data;
    }

    async function markSending(packName) {
      await postLocal("/assist/mark-sending", { pack: packName });
    }

    async function markSent(packName) {
      await postLocal("/assist/mark-sent", { pack: packName });
    }

    async function markFailed(packName, error) {
      if (!packName) return;
      try {
        await postLocal("/assist/mark-failed", { pack: packName, error: String(error.message || error) });
      } catch (_error) {
        // The visible panel already shows the failure; avoid masking the original error.
      }
    }

    async function importResponse(packName, responseText) {
      return await postLocal("/assist/import-response", { pack: packName, responseText });
    }

    function composer() {
      return document.querySelector("#prompt-textarea")
        || document.querySelector("textarea")
        || document.querySelector("[contenteditable='true']");
    }

    function sendButton() {
      return document.querySelector("[data-testid='send-button']")
        || document.querySelector("[data-testid='composer-send-button']")
        || document.querySelector("button[aria-label='Send prompt']")
        || Array.from(document.querySelectorAll("button")).find((button) => /send/i.test(button.getAttribute("aria-label") || ""));
    }

    function stopButton() {
      return document.querySelector("[data-testid='stop-button']")
        || Array.from(document.querySelectorAll("button")).find((button) => /stop/i.test(button.getAttribute("aria-label") || ""));
    }

    function visibleText(node) {
      if (!node) return "";
      const style = window.getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden") return "";
      return (node.innerText || node.textContent || "").trim();
    }

    function assistantNodes() {
      const selectors = [
        "[data-message-author-role='assistant']",
        "article",
        ".markdown"
      ];
      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector)).filter((node) => visibleText(node));
        if (nodes.length) return nodes;
      }
      const main = document.querySelector("main") || document.body;
      return Array.from(main.querySelectorAll("div")).filter((node) => visibleText(node).length > 100);
    }

    function markdownishText(node) {
      const clone = node.cloneNode(true);
      clone.querySelectorAll("pre").forEach((pre) => {
        pre.textContent = `\n\`\`\`\n${pre.innerText || pre.textContent || ""}\n\`\`\`\n`;
      });
      clone.querySelectorAll("li").forEach((li) => {
        if (!/^[-*]\s/.test(li.textContent || "")) li.textContent = `- ${li.textContent || ""}`;
      });
      return visibleText(clone);
    }

    function assistantTexts() {
      return assistantNodes().map(markdownishText).filter(Boolean);
    }

    function captureNewAssistantText(beforeTexts) {
      const afterTexts = assistantTexts();
      if (afterTexts.length > beforeTexts.length) {
        return afterTexts.slice(beforeTexts.length).join("\n\n").trim();
      }
      if (afterTexts.length && afterTexts[afterTexts.length - 1] !== beforeTexts[beforeTexts.length - 1]) {
        return afterTexts[afterTexts.length - 1].trim();
      }
      return "";
    }

    async function fillComposer(text) {
      const target = composer();
      if (!target) throw new Error("ChatGPT composer was not found.");
      target.focus();
      if (target.tagName === "TEXTAREA") {
        target.value = text;
        target.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      const data = new DataTransfer();
      data.setData("text/plain", text);
      target.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
      await sleep(100);
      if (!target.textContent || target.textContent.length < Math.min(20, text.length)) {
        target.textContent = text;
        target.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text.slice(0, 1) }));
      }
    }

    async function waitUntilIdle() {
      const started = Date.now();
      while (Date.now() - started < 600000) {
        if (!stopButton()) return;
        await sleep(1000);
      }
      throw new Error("Timed out waiting for ChatGPT to finish responding.");
    }

    async function waitForAssistantResponse(beforeTexts) {
      const started = Date.now();
      let latest = "";
      while (Date.now() - started < 600000) {
        const captured = captureNewAssistantText(beforeTexts);
        if (captured) latest = captured;
        if (latest && !stopButton()) {
          await sleep(1200);
          return captureNewAssistantText(beforeTexts) || latest;
        }
        await sleep(1000);
      }
      throw new Error("Timed out waiting for a new ChatGPT assistant response.");
    }

    async function sendOne({ confirmFirst = true } = {}) {
      await waitUntilIdle();
      const pack = window.__openlongpdfNextPackOverride || await fetchNextPack();
      window.__openlongpdfNextPackOverride = null;
      if (pack.done) {
        setStatus("No unsent packs remain.");
        return false;
      }
      window.__openlongpdfCurrentPack = pack.pack;
      if (confirmFirst && !confirm(`Send ${pack.pack} to ChatGPT, capture the reply, import it locally, and assemble if this finishes the project?`)) return false;
      setStatus(`Filling ${pack.pack}...`);
      const beforeTexts = assistantTexts();
      await markSending(pack.pack);
      await fillComposer(pack.text);
      await sleep(250);
      const button = sendButton();
      if (!button || button.disabled) {
        await navigator.clipboard.writeText(pack.text);
        throw new Error("Send button was unavailable. Pack text was copied to clipboard instead.");
      }
      button.click();
      await markSent(pack.pack);
      setStatus(`Waiting for ChatGPT response to ${pack.pack}...`);
      const responseText = await waitForAssistantResponse(beforeTexts);
      if (!responseText.trim()) throw new Error(`Could not capture ChatGPT response for ${pack.pack}.`);
      setStatus(`Importing ${pack.pack} response...`);
      const imported = await importResponse(pack.pack, responseText);
      if (imported.assembled) {
        setStatus(`Imported ${pack.pack} and assembled reading notes.`);
      } else {
        setStatus(`Imported ${pack.pack}: ${imported.importedChunkNames.join(", ")}.`);
      }
      return true;
    }

    panel.querySelector("#openlongpdf-send-next").onclick = async () => {
      let currentPack = "";
      try {
        const pack = await fetchNextPack();
        if (pack.done) {
          setStatus("No pending packs remain.");
          return;
        }
        currentPack = pack.pack;
        window.__openlongpdfNextPackOverride = pack;
        await sendOne({ confirmFirst: true });
        window.__openlongpdfNextPackOverride = null;
      } catch (error) {
        await markFailed(currentPack, error);
        setStatus(error.message);
        alert(error.message);
      }
    };

    panel.querySelector("#openlongpdf-auto-send").onclick = async () => {
      if (!confirm("One-time consent: OpenLongPDF will send each remaining pack in this ChatGPT tab, capture each visible assistant reply, POST it to the local GUI for import, and assemble when all packs are imported. Keep this tab open. Continue?")) return;
      let currentPack = "";
      try {
        while (true) {
          const pack = await fetchNextPack();
          if (pack.done) {
            setStatus("All pending packs are imported or no pending packs remain.");
            break;
          }
          currentPack = pack.pack;
          window.__openlongpdfNextPackOverride = pack;
          if (!(await sendOne({ confirmFirst: false }))) break;
          window.__openlongpdfNextPackOverride = null;
          await sleep(1500);
        }
      } catch (error) {
        await markFailed(currentPack, error);
        setStatus(error.message);
        alert(error.message);
      } finally {
        window.__openlongpdfNextPackOverride = null;
      }
    };

    panel.querySelector("#openlongpdf-close").onclick = () => panel.remove();
  }

  globalThis.openLongPDFStartAssist = startAssist;
})();
