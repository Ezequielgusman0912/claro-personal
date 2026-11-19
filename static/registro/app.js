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
  const buttonLabel = upload.querySelector("[data-upload-label]");
  const spinner = upload.querySelector("[data-upload-spinner]");
  const manualLink = upload.querySelector("[data-manual-entry]");
  const fileField = upload.querySelector('input[type="file"]');
  const status = upload.querySelector(".ocr-status");
  const resultMessage = document.querySelector("[data-ocr-result]");
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
      }).catch((error) => {
        libraryPromise = null;
        throw error;
      });
    }
    return libraryPromise;
  }

  function setBusy(busy) {
    const complete = upload.dataset.ocrComplete === "true";
    button.disabled = busy || complete;
    fileField.disabled = busy || complete;
    spinner.hidden = !busy;
    upload.setAttribute("aria-busy", String(busy));
    buttonLabel.textContent = busy
      ? "Cargando datos…"
      : complete
        ? "Comprobante leído"
        : fileField.files.length
          ? "Cargar datos"
          : "Cargar comprobante";
  }

  fileField.addEventListener("change", () => {
    status.textContent = "";
    manualLink.hidden = true;
    resultMessage.hidden = true;
    buttonLabel.textContent = fileField.files.length ? "Cargar datos" : "Cargar comprobante";
  });

  upload.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileField.files[0];
    if (!file) return;
    const validType = ["image/jpeg", "image/png", "image/webp"].includes(file.type)
      || /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!validType || file.size > 8 * 1024 * 1024) {
      window.alert("Elegí una imagen JPG, PNG o WebP de hasta 8 MB.");
      fileField.value = "";
      buttonLabel.textContent = "Cargar comprobante";
      return;
    }

    setBusy(true);
    status.textContent = "Preparando lectura en este dispositivo…";

    let worker;
    try {
      const bitmap = await createImageBitmap(file);
      const tooManyPixels = bitmap.width * bitmap.height > 20_000_000;
      bitmap.close();
      if (tooManyPixels) {
        throw new Error("La imagen es demasiado grande. Elegí una de menos de 20 megapíxeles.");
      }

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
      const result = await worker.recognize(file);
      const text = result.data.text.trim();
      if (!text) {
        throw new Error("No pudimos leer texto. Elegí otro comprobante o cargá los datos a mano.");
      }
      status.textContent = "Completando el formulario…";
      const csrfToken = upload.querySelector("[name=csrfmiddlewaretoken]").value;
      const response = await fetch(upload.action, {
        method: "POST",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-CSRFToken": csrfToken,
        },
        body: new URLSearchParams({
          csrfmiddlewaretoken: csrfToken,
          ocr_text: text.slice(0, 30_000),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "No se pudo cargar la lectura.");
      }
      const fields = {
        amount: "amount",
        date: "date",
        recipient: "recipient",
        operation_id: "operation_id",
        currency: "currency",
        account: "account",
      };
      if (!Object.values(payload.data).some(Boolean)) {
        throw new Error("No encontramos datos reconocibles en este comprobante. Elegí otra imagen o cargá los datos a mano.");
      }
      const amountWasEmpty = !document.querySelector("#id_amount").value;
      let loaded = 0;
      for (const [key, fieldName] of Object.entries(fields)) {
        const value = payload.data[key];
        const field = document.querySelector(`#id_${fieldName}`);
        if (!value || !field) continue;
        if (key === "currency") {
          if (!amountWasEmpty || field.value === value) continue;
        } else if (field.value) {
          continue;
        }
        field.value = value;
        loaded += 1;
      }
      resultMessage.textContent = loaded
        ? "Datos cargados en el formulario. Revisalos: todavía no se guardó el pago. Elegí “Guardar pendiente” o “Confirmar” cuando esté listo."
        : "La lectura encontró datos, pero tus campos ya estaban completos. Revisalos; todavía no se guardó el pago.";
      resultMessage.hidden = false;
      manualLink.hidden = true;
      upload.dataset.ocrComplete = "true";
      document.querySelector("#manual").scrollIntoView({ behavior: "smooth", block: "start" });
      status.textContent = "Datos cargados en el formulario; todavía no se guardaron. Para usar otro comprobante, iniciá un nuevo pago.";
    } catch (error) {
      console.error("Receipt OCR failed:", error);
      const message = error.message || "No pudimos leer esta imagen.";
      status.textContent = `${message} La imagen no se envía ni se guarda.`;
      window.alert(`${message}\n\nPodés elegir otro comprobante en esta misma pantalla o cargar los datos a mano.`);
      fileField.value = "";
      manualLink.hidden = false;
    } finally {
      if (worker) await worker.terminate();
      setBusy(false);
    }
  });
})();
