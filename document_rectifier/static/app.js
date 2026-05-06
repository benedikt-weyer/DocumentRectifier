const canvas = document.getElementById("canvas");
const context = canvas.getContext("2d");
const loupeElement = document.getElementById("loupe");
const loupeCanvas = document.getElementById("loupe-canvas");
const loupeContext = loupeCanvas.getContext("2d");
const statusElement = document.getElementById("status");
const progressLabelElement = document.getElementById("progress-label");
const progressRemainingElement = document.getElementById("progress-remaining");
const progressTrackElement = document.getElementById("progress-track");
const modePickerElement = document.getElementById("mode-picker");
const workspaceElement = document.getElementById("workspace");
const chooseDocumentButton = document.getElementById("choose-document");
const chooseAspectRatioButton = document.getElementById("choose-aspect-ratio");
const imageNameElement = document.getElementById("image-name");
const documentGuideElement = document.getElementById("document-guide");
const aspectGuideElement = document.getElementById("aspect-guide");
const pointsSectionElement = document.getElementById("points-section");
const pointsElement = document.getElementById("points");
const aspectControlsElement = document.getElementById("aspect-controls");
const aspectRatiosInput = document.getElementById("aspect-ratios");
const selectedRatioElement = document.getElementById("selected-ratio");
const shiftControl = document.getElementById("shift-control");
const shiftLabelElement = document.getElementById("shift-label");
const shiftValueElement = document.getElementById("shift-value");
const shiftStartElement = document.getElementById("shift-start");
const shiftEndElement = document.getElementById("shift-end");
const marginControl = document.getElementById("margin-control");
const marginValueElement = document.getElementById("margin-value");
const actionsElement = document.getElementById("actions");
const saveButton = document.getElementById("save");
const resetButton = document.getElementById("reset");
const skipButton = document.getElementById("skip");
const quitButton = document.getElementById("quit");
const autoDetectButton = document.getElementById("auto-detect");
const image = new Image();

const DOCUMENT_MODE = "document";
const ASPECT_RATIO_MODE = "aspect-ratio";
const HANDLE_RADIUS = 12;
const HANDLE_HIT_PADDING = 10;
const LOUPE_ZOOM = 4;
const LOUPE_OFFSET_X = 24;
const LOUPE_OFFSET_Y = 24;
const DRAG_DAMPING = 0.35;

let currentScreen = "idle";
let currentWorkflowMode = null;
let currentVersion = null;
let currentImageName = null;
let scale = 1;
let points = [];
let dragIndex = null;
let activePointerId = null;
let dragOriginPoint = null;
let dragOriginClient = null;
let aspectRatioDefinitions = [];
let shiftPercent = 50;
let marginPercent = 0;

function setStatus(text) {
    statusElement.textContent = text;
}

function getErrorMessage(error) {
    if (error instanceof Error) {
        return error.message;
    }

    return String(error);
}

function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
}

function formatPercent(value) {
    const rounded = Math.round(value * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function setHidden(element, hidden) {
    element.classList.toggle("hidden", hidden);
}

function clearCanvas() {
    context.clearRect(0, 0, canvas.width, canvas.height);
}

function hideLoupe() {
    loupeElement.classList.remove("visible");
}

function positionLoupe(clientX, clientY) {
    const left = clamp(
        clientX + LOUPE_OFFSET_X,
        12,
        window.innerWidth - loupeElement.offsetWidth - 12,
    );
    const top = clamp(
        clientY - loupeElement.offsetHeight - LOUPE_OFFSET_Y,
        12,
        window.innerHeight - loupeElement.offsetHeight - 12,
    );
    loupeElement.style.left = `${left}px`;
    loupeElement.style.top = `${top}px`;
}

function drawLoupe(point, clientX, clientY) {
    if (currentWorkflowMode !== DOCUMENT_MODE || !image.naturalWidth || !image.naturalHeight) {
        return;
    }

    const sourceSize = loupeCanvas.width / LOUPE_ZOOM;
    const maxSourceX = Math.max(image.naturalWidth - sourceSize, 0);
    const maxSourceY = Math.max(image.naturalHeight - sourceSize, 0);
    const sourceX = clamp(point.x - sourceSize / 2, 0, maxSourceX);
    const sourceY = clamp(point.y - sourceSize / 2, 0, maxSourceY);

    loupeContext.clearRect(0, 0, loupeCanvas.width, loupeCanvas.height);
    loupeContext.imageSmoothingEnabled = false;
    loupeContext.drawImage(
        image,
        sourceX,
        sourceY,
        sourceSize,
        sourceSize,
        0,
        0,
        loupeCanvas.width,
        loupeCanvas.height,
    );

    loupeContext.save();
    loupeContext.strokeStyle = "rgba(181, 84, 45, 0.95)";
    loupeContext.lineWidth = 2;
    loupeContext.beginPath();
    loupeContext.moveTo(loupeCanvas.width / 2, 0);
    loupeContext.lineTo(loupeCanvas.width / 2, loupeCanvas.height);
    loupeContext.moveTo(0, loupeCanvas.height / 2);
    loupeContext.lineTo(loupeCanvas.width, loupeCanvas.height / 2);
    loupeContext.stroke();
    loupeContext.restore();

    positionLoupe(clientX, clientY);
    loupeElement.classList.add("visible");
}

function getCanvasPoint(event) {
    const bounds = canvas.getBoundingClientRect();
    return {
        x: clamp(
            (event.clientX - bounds.left) / scale,
            0,
            Math.max(image.naturalWidth - 1, 0),
        ),
        y: clamp(
            (event.clientY - bounds.top) / scale,
            0,
            Math.max(image.naturalHeight - 1, 0),
        ),
    };
}

function getPointHitIndex(targetPoint) {
    const hitRadius = (HANDLE_RADIUS + HANDLE_HIT_PADDING) / Math.max(scale, 0.001);
    return points.findIndex((point) => Math.hypot(point.x - targetPoint.x, point.y - targetPoint.y) <= hitRadius);
}

function beginDrag(index, event) {
    dragIndex = index;
    activePointerId = event.pointerId;
    dragOriginPoint = { ...points[index] };
    dragOriginClient = { x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
    canvas.style.cursor = "grabbing";
    renderPoints();
    draw();
    drawLoupe(points[dragIndex], event.clientX, event.clientY);
}

function updateCanvasCursor(event) {
    if (!image.naturalWidth) {
        canvas.style.cursor = "crosshair";
        return;
    }

    if (currentWorkflowMode !== DOCUMENT_MODE) {
        canvas.style.cursor = "default";
        return;
    }

    if (dragIndex !== null) {
        canvas.style.cursor = "grabbing";
        return;
    }

    const point = getCanvasPoint(event);
    if (getPointHitIndex(point) !== -1) {
        canvas.style.cursor = "grab";
        return;
    }

    canvas.style.cursor = points.length < 4 ? "crosshair" : "default";
}

function parseAspectRatios(rawText) {
    return rawText
        .split(/[\n,]+/)
        .map((entry) => entry.trim())
        .filter(Boolean)
        .map((entry) => {
            const match = entry.match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
            if (!match) {
                return null;
            }

            const width = Number(match[1]);
            const height = Number(match[2]);
            if (width <= 0 || height <= 0) {
                return null;
            }

            return {
                label: `${match[1]}:${match[2]}`,
                width,
                height,
                value: width / height,
            };
        })
        .filter((entry) => entry !== null);
}

function computeInnerBounds(width, height, margin) {
    const normalizedMargin = clamp(margin, 0, 45) / 100;
    const marginX = width * normalizedMargin;
    const marginY = height * normalizedMargin;
    return {
        left: marginX,
        top: marginY,
        right: width - marginX,
        bottom: height - marginY,
        width: Math.max(width - (marginX * 2), 1),
        height: Math.max(height - (marginY * 2), 1),
    };
}

function chooseClosestAspectRatio(definitions, width, height, margin) {
    if (definitions.length === 0) {
        return null;
    }

    const inner = computeInnerBounds(width, height, margin);
    const imageRatio = inner.width / inner.height;

    return definitions.reduce((best, definition) => {
        if (best === null) {
            return definition;
        }

        const bestDistance = Math.abs(best.value - imageRatio);
        const currentDistance = Math.abs(definition.value - imageRatio);
        return currentDistance < bestDistance ? definition : best;
    }, null);
}

function computeAspectCropRect(width, height, ratioDefinition, shift, margin) {
    const inner = computeInnerBounds(width, height, margin);
    const targetRatio = ratioDefinition.value;
    const imageRatio = inner.width / inner.height;
    const shiftFactor = clamp(shift, 0, 100) / 100;

    let left = inner.left;
    let top = inner.top;
    let right = inner.right;
    let bottom = inner.bottom;
    let axis = "none";

    if (imageRatio > targetRatio) {
        const cropWidth = inner.height * targetRatio;
        const slackX = Math.max(inner.width - cropWidth, 0);
        left = inner.left + (slackX * shiftFactor);
        right = left + cropWidth;
        axis = "x";
    } else if (imageRatio < targetRatio) {
        const cropHeight = inner.width / targetRatio;
        const slackY = Math.max(inner.height - cropHeight, 0);
        top = inner.top + (slackY * shiftFactor);
        bottom = top + cropHeight;
        axis = "y";
    }

    return {
        ratio: ratioDefinition,
        axis,
        left,
        top,
        right,
        bottom,
        inner,
    };
}

function getAspectCropState() {
    if (currentWorkflowMode !== ASPECT_RATIO_MODE || !image.naturalWidth || !image.naturalHeight) {
        return null;
    }

    const selectedRatio = chooseClosestAspectRatio(
        aspectRatioDefinitions,
        image.naturalWidth,
        image.naturalHeight,
        marginPercent,
    );
    if (selectedRatio === null) {
        return null;
    }

    return computeAspectCropRect(
        image.naturalWidth,
        image.naturalHeight,
        selectedRatio,
        shiftPercent,
        marginPercent,
    );
}

function syncActionState() {
    const isDocumentMode = currentWorkflowMode === DOCUMENT_MODE;
    const isAspectMode = currentWorkflowMode === ASPECT_RATIO_MODE;
    autoDetectButton.disabled = !isDocumentMode || !image.naturalWidth;
    saveButton.disabled = true;

    if (isDocumentMode) {
        saveButton.disabled = points.length !== 4;
        return;
    }

    if (isAspectMode) {
        saveButton.disabled = getAspectCropState() === null;
    }
}

function renderPoints() {
    if (currentWorkflowMode !== DOCUMENT_MODE) {
        pointsElement.innerHTML = "<span>Aspect mode uses the crop overlay instead of corner points.</span>";
        syncActionState();
        return;
    }

    if (points.length === 0) {
        pointsElement.innerHTML = "<span>No points selected yet.</span>";
    } else {
        pointsElement.innerHTML = points
            .map((point, index) => `<span><strong>${index + 1}.</strong> (${Math.round(point.x)}, ${Math.round(point.y)})</span>`)
            .join("");
    }

    syncActionState();
}

function renderAspectControls() {
    shiftPercent = Number(shiftControl.value);
    marginPercent = Number(marginControl.value);
    shiftValueElement.textContent = `${formatPercent(shiftPercent)}%`;
    marginValueElement.textContent = `${formatPercent(marginPercent)}%`;

    if (currentWorkflowMode !== ASPECT_RATIO_MODE) {
        syncActionState();
        return;
    }

    const cropState = getAspectCropState();
    if (aspectRatioDefinitions.length === 0) {
        selectedRatioElement.textContent = "Enter one or more ratios like 1:1, 4:5, 16:9.";
        shiftLabelElement.textContent = "Shift crop";
        shiftStartElement.textContent = "Left";
        shiftEndElement.textContent = "Right";
        shiftControl.disabled = true;
        syncActionState();
        return;
    }

    if (cropState === null) {
        selectedRatioElement.textContent = "Load an image to preview the closest ratio.";
        shiftControl.disabled = true;
        syncActionState();
        return;
    }

    selectedRatioElement.textContent = `Closest ratio: ${cropState.ratio.label}`;
    if (cropState.axis === "x") {
        shiftLabelElement.textContent = "Shift crop horizontally";
        shiftStartElement.textContent = "Left";
        shiftEndElement.textContent = "Right";
        shiftControl.disabled = false;
    } else if (cropState.axis === "y") {
        shiftLabelElement.textContent = "Shift crop vertically";
        shiftStartElement.textContent = "Top";
        shiftEndElement.textContent = "Bottom";
        shiftControl.disabled = false;
    } else {
        shiftLabelElement.textContent = "Shift crop";
        shiftStartElement.textContent = "Centered";
        shiftEndElement.textContent = "Centered";
        shiftControl.disabled = true;
    }

    syncActionState();
}

function renderModePicker(availableModes) {
    chooseDocumentButton.disabled = !availableModes.includes(DOCUMENT_MODE);
    chooseAspectRatioButton.disabled = !availableModes.includes(ASPECT_RATIO_MODE);
}

function renderLayout() {
    const isModePicker = currentScreen === "mode-selection";
    const isDocumentMode = currentWorkflowMode === DOCUMENT_MODE;
    const isAspectMode = currentWorkflowMode === ASPECT_RATIO_MODE;

    setHidden(modePickerElement, !isModePicker);
    setHidden(workspaceElement, isModePicker);
    setHidden(documentGuideElement, !isDocumentMode);
    setHidden(pointsSectionElement, !isDocumentMode);
    setHidden(aspectGuideElement, !isAspectMode);
    setHidden(aspectControlsElement, !isAspectMode);
    setHidden(actionsElement, !(isDocumentMode || isAspectMode));
    setHidden(autoDetectButton, !isDocumentMode);

    if (!isDocumentMode) {
        hideLoupe();
    }
}

function renderProgress(state) {
    const totalImages = Number(state.totalImages || 0);
    const completedImages = Number(state.completedImages || 0);
    const currentImageNumber = Number(state.currentImageNumber || 0);
    const imagesLeft = Number(state.imagesLeft || 0);

    if (totalImages <= 0) {
        progressLabelElement.textContent = "No images queued";
        progressRemainingElement.textContent = "0 left";
        progressTrackElement.value = 0;
        return;
    }

    const percentComplete = Math.round((completedImages / totalImages) * 100);
    if (state.hasImage && currentImageNumber > 0) {
        progressLabelElement.textContent = `Image ${currentImageNumber} of ${totalImages}`;
    } else {
        progressLabelElement.textContent = `${completedImages} of ${totalImages} processed`;
    }
    progressRemainingElement.textContent = `${imagesLeft} left`;
    progressTrackElement.value = percentComplete;
}

function drawDocumentOverlay() {
    if (points.length > 1) {
        context.beginPath();
        context.lineWidth = 2;
        context.strokeStyle = "#b5542d";
        context.moveTo(points[0].x * scale, points[0].y * scale);
        for (let index = 1; index < points.length; index += 1) {
            context.lineTo(points[index].x * scale, points[index].y * scale);
        }
        if (points.length === 4) {
            context.closePath();
        }
        context.stroke();
    }

    points.forEach((point, index) => {
        const scaledX = point.x * scale;
        const scaledY = point.y * scale;
        context.save();
        context.strokeStyle = dragIndex === index ? "#b5542d" : "#ffcc66";
        context.lineWidth = dragIndex === index ? 3 : 2;
        context.beginPath();
        context.moveTo(scaledX - 12, scaledY);
        context.lineTo(scaledX + 12, scaledY);
        context.moveTo(scaledX, scaledY - 12);
        context.lineTo(scaledX, scaledY + 12);
        context.stroke();

        context.beginPath();
        context.arc(scaledX, scaledY, 4, 0, Math.PI * 2);
        context.stroke();
        context.restore();
        context.fillStyle = "#1f2933";
        context.font = "bold 18px IBM Plex Sans, sans-serif";
        context.fillText(String(index + 1), scaledX + 12, scaledY - 12);
    });
}

function drawAspectOverlay() {
    const cropState = getAspectCropState();
    if (cropState === null) {
        return;
    }

    const cropLeft = cropState.left * scale;
    const cropTop = cropState.top * scale;
    const cropWidth = (cropState.right - cropState.left) * scale;
    const cropHeight = (cropState.bottom - cropState.top) * scale;
    const innerLeft = cropState.inner.left * scale;
    const innerTop = cropState.inner.top * scale;
    const innerWidth = cropState.inner.width * scale;
    const innerHeight = cropState.inner.height * scale;

    context.save();
    context.fillStyle = "rgba(31, 41, 51, 0.38)";
    context.beginPath();
    context.rect(0, 0, canvas.width, canvas.height);
    context.rect(cropLeft, cropTop, cropWidth, cropHeight);
    context.fill("evenodd");

    context.strokeStyle = "rgba(255, 255, 255, 0.55)";
    context.setLineDash([8, 8]);
    context.lineWidth = 1.5;
    context.strokeRect(innerLeft, innerTop, innerWidth, innerHeight);

    context.setLineDash([]);
    context.strokeStyle = "#b5542d";
    context.lineWidth = 3;
    context.strokeRect(cropLeft, cropTop, cropWidth, cropHeight);
    context.restore();
}

function draw() {
    if (!image.naturalWidth || !image.naturalHeight) {
        return;
    }

    const maxWidth = Math.max(window.innerWidth - 440, 320);
    const maxHeight = Math.max(window.innerHeight - 220, 320);
    scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
    canvas.width = Math.round(image.naturalWidth * scale);
    canvas.height = Math.round(image.naturalHeight * scale);

    clearCanvas();
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

    if (currentWorkflowMode === DOCUMENT_MODE) {
        drawDocumentOverlay();
    }

    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        drawAspectOverlay();
    }
}

async function fetchState() {
    const response = await fetch("/state", { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`State request failed: ${response.status}`);
    }

    const state = await response.json();
    renderProgress(state);
    currentScreen = state.screen || "idle";
    currentWorkflowMode = state.workflowMode ?? null;
    renderLayout();

    if (currentScreen === "mode-selection") {
        currentVersion = null;
        currentImageName = null;
        points = [];
        dragIndex = null;
        activePointerId = null;
        hideLoupe();
        renderModePicker(state.availableModes || []);
        imageNameElement.textContent = "Choose a workflow";
        renderPoints();
        renderAspectControls();
        setStatus(state.message);
        clearCanvas();
        return;
    }

    if (!state.hasImage) {
        currentVersion = null;
        currentImageName = null;
        points = [];
        dragIndex = null;
        activePointerId = null;
        hideLoupe();
        renderPoints();
        renderAspectControls();
        imageNameElement.textContent = state.message;
        setStatus(state.message);
        clearCanvas();
        return;
    }

    if (state.version !== currentVersion) {
        const changedMode = currentWorkflowMode !== (state.workflowMode ?? null);
        currentVersion = state.version;
        currentImageName = state.imageName;
        currentWorkflowMode = state.workflowMode ?? null;
        points = [];
        dragIndex = null;
        activePointerId = null;
        dragOriginPoint = null;
        dragOriginClient = null;
        hideLoupe();
        imageNameElement.textContent = state.imageName;

        if (currentWorkflowMode === DOCUMENT_MODE) {
            setStatus(`Select corners for ${state.imageName}`);
        } else if (currentWorkflowMode === ASPECT_RATIO_MODE) {
            if (changedMode || !aspectRatiosInput.value.trim()) {
                aspectRatiosInput.value = (state.defaultAspectRatios || []).join(", ");
                aspectRatioDefinitions = parseAspectRatios(aspectRatiosInput.value);
            }
            shiftPercent = 50;
            marginPercent = 0;
            shiftControl.value = "50";
            marginControl.value = "0";
            setStatus(`Adjust crop for ${state.imageName}`);
        }

        renderLayout();
        renderPoints();
        renderAspectControls();
        image.src = `/image?v=${state.version}`;
    }
}

async function chooseMode(mode) {
    const response = await fetch("/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `Mode selection failed: ${response.status}`);
    }
}

async function autoDetectCorners() {
    if (currentWorkflowMode !== DOCUMENT_MODE || !image.naturalWidth) {
        return;
    }

    autoDetectButton.disabled = true;
    try {
        const response = await fetch("/auto-detect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });

        if (!response.ok) {
            const errorText = await response.text();
            setStatus(errorText || `Auto detect failed: ${response.status}`);
            return;
        }

        const payload = await response.json();
        points = payload.points.map((point) => ({
            x: Number(point.x),
            y: Number(point.y),
        }));
        dragIndex = null;
        activePointerId = null;
        dragOriginPoint = null;
        dragOriginClient = null;
        hideLoupe();
        renderPoints();
        draw();
        setStatus(payload.message || `Auto-detected corners for ${currentImageName}`);
    } catch (error) {
        setStatus(getErrorMessage(error));
    } finally {
        renderPoints();
    }
}

async function submit(action) {
    let payload = { action };

    if (currentWorkflowMode === DOCUMENT_MODE) {
        if (action === "save" && points.length !== 4) {
            setStatus("Select exactly four points before saving.");
            return;
        }
        payload = { action, points };
    } else if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        const cropState = getAspectCropState();
        if (action === "save" && cropState === null) {
            setStatus("Enter at least one valid aspect ratio before saving.");
            return;
        }
        if (cropState !== null) {
            payload = {
                action,
                ratioLabel: cropState.ratio.label,
                ratioWidth: cropState.ratio.width,
                ratioHeight: cropState.ratio.height,
                shiftPercent,
                marginPercent,
            };
        }
    } else {
        return;
    }

    saveButton.disabled = true;
    const response = await fetch("/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorText = await response.text();
        setStatus(errorText || `Submission failed: ${response.status}`);
        renderPoints();
        renderAspectControls();
        return;
    }

    setStatus(action === "save" ? "Saved. Waiting for next image..." : "Advancing...");
}

canvas.addEventListener("pointerdown", (event) => {
    if (currentWorkflowMode !== DOCUMENT_MODE || !image.naturalWidth) {
        return;
    }

    const point = getCanvasPoint(event);
    const hitIndex = getPointHitIndex(point);

    if (hitIndex !== -1) {
        beginDrag(hitIndex, event);
        return;
    }

    if (points.length >= 4) {
        return;
    }

    points.push({ x: Math.round(point.x), y: Math.round(point.y) });
    beginDrag(points.length - 1, event);
});

canvas.addEventListener("pointermove", (event) => {
    if (currentWorkflowMode !== DOCUMENT_MODE) {
        canvas.style.cursor = image.naturalWidth ? "default" : "crosshair";
        return;
    }

    if (dragIndex === null || activePointerId !== event.pointerId) {
        if (image.naturalWidth && points.length < 4) {
            const point = getCanvasPoint(event);
            drawLoupe(point, event.clientX, event.clientY);
        } else if (dragIndex === null) {
            hideLoupe();
        }
        updateCanvasCursor(event);
        return;
    }

    const deltaX = (event.clientX - dragOriginClient.x) / Math.max(scale, 0.001);
    const deltaY = (event.clientY - dragOriginClient.y) / Math.max(scale, 0.001);
    points[dragIndex] = {
        x: clamp(dragOriginPoint.x + (deltaX * DRAG_DAMPING), 0, Math.max(image.naturalWidth - 1, 0)),
        y: clamp(dragOriginPoint.y + (deltaY * DRAG_DAMPING), 0, Math.max(image.naturalHeight - 1, 0)),
    };
    renderPoints();
    draw();
    drawLoupe(points[dragIndex], event.clientX, event.clientY);
});

function finishDrag(event) {
    if (currentWorkflowMode !== DOCUMENT_MODE || dragIndex === null || activePointerId !== event.pointerId) {
        return;
    }

    if (canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
    }
    dragIndex = null;
    activePointerId = null;
    dragOriginPoint = null;
    dragOriginClient = null;
    hideLoupe();
    updateCanvasCursor(event);
    renderPoints();
    draw();
}

canvas.addEventListener("pointerup", finishDrag);
canvas.addEventListener("pointercancel", finishDrag);
canvas.addEventListener("pointerleave", (event) => {
    if (currentWorkflowMode !== DOCUMENT_MODE) {
        return;
    }

    if (dragIndex === null) {
        canvas.style.cursor = points.length < 4 ? "crosshair" : "default";
        hideLoupe();
        return;
    }

    drawLoupe(points[dragIndex], event.clientX, event.clientY);
});

chooseDocumentButton.addEventListener("click", async () => {
    try {
        await chooseMode(DOCUMENT_MODE);
        setStatus("Loading document workflow...");
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
});

chooseAspectRatioButton.addEventListener("click", async () => {
    try {
        await chooseMode(ASPECT_RATIO_MODE);
        setStatus("Loading aspect ratio workflow...");
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
});

resetButton.addEventListener("click", () => {
    if (currentWorkflowMode === DOCUMENT_MODE) {
        points = [];
        dragIndex = null;
        activePointerId = null;
        dragOriginPoint = null;
        dragOriginClient = null;
        hideLoupe();
        renderPoints();
        draw();
        setStatus(currentImageName ? `Reset points for ${currentImageName}` : "Waiting for image...");
        return;
    }

    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        shiftPercent = 50;
        marginPercent = 0;
        shiftControl.value = "50";
        marginControl.value = "0";
        renderAspectControls();
        draw();
        setStatus(currentImageName ? `Reset crop controls for ${currentImageName}` : "Waiting for image...");
    }
});

saveButton.addEventListener("click", async () => {
    try {
        await submit("save");
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
});

skipButton.addEventListener("click", async () => {
    try {
        await submit("skip");
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
});

quitButton.addEventListener("click", async () => {
    try {
        await submit("quit");
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
});

autoDetectButton.addEventListener("click", autoDetectCorners);

aspectRatiosInput.addEventListener("input", () => {
    aspectRatioDefinitions = parseAspectRatios(aspectRatiosInput.value);
    renderAspectControls();
    draw();
});

shiftControl.addEventListener("input", () => {
    renderAspectControls();
    draw();
});

marginControl.addEventListener("input", () => {
    renderAspectControls();
    draw();
});

window.addEventListener("resize", () => {
    draw();
    hideLoupe();
});

image.addEventListener("load", () => {
    draw();
    renderPoints();
    renderAspectControls();
});

renderPoints();
renderAspectControls();
setInterval(() => {
    void refreshState();
}, 600);

async function refreshState() {
    try {
        await fetchState();
    } catch (error) {
        setStatus(getErrorMessage(error));
    }
}

await refreshState();