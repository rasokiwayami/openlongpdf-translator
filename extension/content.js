(async () => {
  const params = new URLSearchParams(location.search);
  const server = params.get("openlongpdf_server");
  const token = params.get("openlongpdf_token");
  if (!server || !token) return;

  if (globalThis.chrome?.storage?.local) {
    await chrome.storage.local.set({
      openlongpdfServer: server,
      openlongpdfToken: token,
      openlongpdfUpdatedAt: new Date().toISOString()
    });
  }

  params.delete("openlongpdf_server");
  params.delete("openlongpdf_token");
  const clean = `${location.pathname}${params.toString() ? `?${params}` : ""}${location.hash}`;
  history.replaceState(null, "", clean || "/");

  globalThis.openLongPDFStartAssist({ server, token });
})();
