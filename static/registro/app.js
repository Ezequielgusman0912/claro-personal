(() => {
  const kind = document.querySelector("#id_kind");
  const destination = document.querySelector("[data-destination]");
  const destinationInput = document.querySelector("#id_destination_account");
  function updateDestination() {
    if (!kind || !destination) return;
    const isTransfer = kind.value === "transfer";
    destination.hidden = !isTransfer;
    if (!isTransfer && destinationInput) destinationInput.value = "";
  }
  if (kind) kind.addEventListener("change", updateDestination);
  updateDestination();

  const upload = document.querySelector(".upload-form[data-worker-url]");
  if (!upload) return;

  const button = upload.querySelector("[data-upload-button]");
  const manualLink = upload.querySelector("[data-manual-entry]");
  const textField = upload.querySelector('[name="ocr_text"]');
  const fileField = upload.querySelector('input[type="file"]');
  const status = upload.querySelector(".ocr-status");
  let libraryPromise;

  function loadLibrary() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (!libraryPromise) {
      libraryPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = upload.dataset.libraryUrl;
        script.onload = () => window.Tesseract
          ? resolve(window.Tesseract)
          : reject(new Error("La librería OCR no está disponible."));
        script.onerror = () => reject(new Error("No se pudo cargar el lector local."));
        document.head.append(script);
      });
    }
    return libraryPromise;
  }

  upload.addEventListener("submit", async (event) => {
    if (upload.dataset.ocrReady === "true") {
      button.disabled = true;
      fileField.disabled = true;
      status.textContent = "Guardando solo los datos leídos…";
      return;
    }
    event.preventDefault();
    if (!fileField.files.length) return;
    button.disabled = true;
    button.textContent = "Leyendo comprobante…";
    status.textContent = "Preparando lectura en este dispositivo…";

    let worker;
    try {
      const Tesseract = await loadLibrary();
      worker = await Tesseract.createWorker("spa", 1, {
        workerPath: upload.dataset.workerUrl,
        corePath: upload.dataset.coreUrl,
        langPath: upload.dataset.languageUrl,
        gzip: true,
        logger(message) {
          if (message.status === "recognizing text") {
            status.textContent = `Leyendo comprobante… ${Math.round(message.progress * 100)}%`;
          } else if (message.status) {
            status.textContent = "Preparando lector en este dispositivo…";
          }
        },
      });
      const result = await worker.recognize(fileField.files[0]);
      if (!result.data.text.trim()) {
        throw new Error("No pudimos leer texto en esta imagen.");
      }
      textField.value = result.data.text.slice(0, 30_000);
      upload.dataset.ocrReady = "true";
      status.textContent = "Lectura lista. Guardando solo los datos detectados…";
      upload.requestSubmit(button);
    } catch (error) {
      console.error("Receipt OCR failed:", error);
      status.textContent = `${error.message || "No pudimos leer esta imagen."} La imagen no se guarda. Podés intentar de nuevo o cargar los datos a mano mirando el original.`;
      button.disabled = false;
      button.textContent = "Reintentar lectura";
      manualLink.hidden = false;
    } finally {
      if (worker) await worker.terminate();
    }
  });
})();
