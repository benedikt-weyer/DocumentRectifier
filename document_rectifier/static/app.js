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
const ratioOptionsElement = document.getElementById("ratio-options");
const zoomControl = document.getElementById("zoom-control");
const zoomValueElement = document.getElementById("zoom-value");
const marginControl = document.getElementById("margin-control");
const marginValueElement = document.getElementById("margin-value");
const rotateDialElement = document.getElementById("rotate-dial");
const dialTrackElement = document.getElementById("dial-track");
const dialCanvas = document.getElementById("dial-canvas");
const dialContext = dialCanvas.getContext("2d");
const dialValueElement = document.getElementById("dial-value");
const rotateResetButton = document.getElementById("rotate-reset");
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
const ROTATE_MAX_DEGREES = 10;
const ROTATE_PIXELS_PER_DEGREE = 8;
const ZOOM_MIN_PERCENT = 100;
const ZOOM_MAX_PERCENT = 300;

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
let selectedRatioLabel = null;
let marginPercent = 0;
let zoomPercent = 100;
let cropCenterX = null;
let cropCenterY = null;
let aspectDragActive = false;
let aspectDragPointerId = null;
let aspectDragOriginCenter = null;
let aspectDragOriginClient = null;
let rotationDegrees = 0;
let dialDragOriginAngle = null;
let dialDragOriginClientX = null;
let dialDragPointerId = null;

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

function isPointInCropRect(point, cropState) {
    return (
        point.x >= cropState.left
        && point.x <= cropState.right
        && point.y >= cropState.top
        && point.y <= cropState.bottom
    );
}

function updateCanvasCursor(event) {
    if (!image.naturalWidth) {
        canvas.style.cursor = "crosshair";
        return;
    }

    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        if (aspectDragActive) {
            canvas.style.cursor = "grabbing";
            return;
        }
        const cropState = getAspectCropState();
        const point = getCanvasPoint(event);
        canvas.style.cursor = cropState !== null && isPointInCropRect(point, cropState) ? "grab" : "default";
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

function resolveActiveRatio(definitions, width, height, margin) {
    const overridden = selectedRatioLabel !== null
        ? definitions.find((definition) => definition.label === selectedRatioLabel)
        : undefined;
    return overridden ?? chooseClosestAspectRatio(definitions, width, height, margin);
}

function computeMaxCropSize(inner, targetRatio) {
    const imageRatio = inner.width / inner.height;
    if (imageRatio > targetRatio) {
        return { width: inner.height * targetRatio, height: inner.height };
    }
    return { width: inner.width, height: inner.width / targetRatio };
}

function clampCenter(value, innerMin, innerMax, cropSize) {
    const low = innerMin + (cropSize / 2);
    const high = innerMax - (cropSize / 2);
    if (low > high) {
        return (innerMin + innerMax) / 2;
    }
    return clamp(value, low, high);
}

function computeAspectCropRect(width, height, ratioDefinition, zoom, margin, centerX, centerY) {
    const inner = computeInnerBounds(width, height, margin);
    const maxCrop = computeMaxCropSize(inner, ratioDefinition.value);
    const zoomScale = ZOOM_MIN_PERCENT / clamp(zoom, ZOOM_MIN_PERCENT, ZOOM_MAX_PERCENT);
    const cropWidth = Math.max(maxCrop.width * zoomScale, 1);
    const cropHeight = Math.max(maxCrop.height * zoomScale, 1);

    const defaultCenterX = inner.left + (inner.width / 2);
    const defaultCenterY = inner.top + (inner.height / 2);
    const resolvedCenterX = clampCenter(
        centerX === null ? defaultCenterX : centerX,
        inner.left,
        inner.right,
        cropWidth,
    );
    const resolvedCenterY = clampCenter(
        centerY === null ? defaultCenterY : centerY,
        inner.top,
        inner.bottom,
        cropHeight,
    );

    const left = resolvedCenterX - (cropWidth / 2);
    const top = resolvedCenterY - (cropHeight / 2);

    return {
        ratio: ratioDefinition,
        left,
        top,
        right: left + cropWidth,
        bottom: top + cropHeight,
        centerX: resolvedCenterX,
        centerY: resolvedCenterY,
        inner,
    };
}

function getAspectCropState() {
    if (currentWorkflowMode !== ASPECT_RATIO_MODE || !image.naturalWidth || !image.naturalHeight) {
        return null;
    }

    const selectedRatio = resolveActiveRatio(
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
        zoomPercent,
        marginPercent,
        cropCenterX,
        cropCenterY,
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
    zoomPercent = Number(zoomControl.value);
    marginPercent = Number(marginControl.value);
    zoomValueElement.textContent = `${(zoomPercent / 100).toFixed(1)}x`;
    marginValueElement.textContent = `${formatPercent(marginPercent)}%`;

    if (currentWorkflowMode !== ASPECT_RATIO_MODE) {
        syncActionState();
        return;
    }

    renderRatioOptions();

    const cropState = getAspectCropState();
    if (aspectRatioDefinitions.length === 0) {
        selectedRatioElement.textContent = "Enter one or more ratios like 1:1, 4:5, 16:9.";
        zoomControl.disabled = true;
        syncActionState();
        return;
    }

    if (cropState === null) {
        selectedRatioElement.textContent = "Load an image to preview the closest ratio.";
        zoomControl.disabled = true;
        syncActionState();
        return;
    }

    zoomControl.disabled = false;
    const isOverride = aspectRatioDefinitions.some((definition) => definition.label === selectedRatioLabel);
    selectedRatioElement.textContent = isOverride
        ? `Using ${cropState.ratio.label} for this image — drag the cutout to reposition it.`
        : `Closest ratio: ${cropState.ratio.label} — drag the cutout to reposition it.`;

    syncActionState();
}

function renderRatioOptions() {
    if (aspectRatioDefinitions.length === 0) {
        ratioOptionsElement.innerHTML = "";
        setHidden(ratioOptionsElement, true);
        return;
    }

    const activeLabel = aspectRatioDefinitions.some((definition) => definition.label === selectedRatioLabel)
        ? selectedRatioLabel
        : null;

    const autoChip = `<button type="button" class="ratio-chip${activeLabel === null ? " active" : ""}" data-ratio-label="">Auto</button>`;
    const chips = aspectRatioDefinitions
        .map((definition) => {
            const isActive = activeLabel === definition.label;
            return `<button type="button" class="ratio-chip${isActive ? " active" : ""}" data-ratio-label="${definition.label}">${definition.label}</button>`;
        })
        .join("");

    ratioOptionsElement.innerHTML = autoChip + chips;
    setHidden(ratioOptionsElement, false);
}

function setRotationDegrees(value) {
    const rounded = Math.round(clamp(value, -ROTATE_MAX_DEGREES, ROTATE_MAX_DEGREES) * 10) / 10;
    rotationDegrees = rounded;
    dialTrackElement.setAttribute("aria-valuenow", String(rounded));
    dialValueElement.textContent = `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}°`;
    drawRotateDial();
    draw();
}

function drawRotateDial() {
    const width = dialTrackElement.clientWidth;
    const height = dialCanvas.height;
    if (width === 0) {
        return;
    }

    dialCanvas.width = width;
    const centerX = width / 2;
    const centerY = height / 2;

    dialContext.clearRect(0, 0, width, height);
    dialContext.strokeStyle = "rgba(31, 41, 51, 0.35)";
    dialContext.fillStyle = "rgba(31, 41, 51, 0.55)";
    dialContext.font = "11px IBM Plex Sans, sans-serif";
    dialContext.textAlign = "center";

    const halfSpan = Math.ceil((width / 2) / ROTATE_PIXELS_PER_DEGREE) + 1;
    for (let degree = -halfSpan; degree <= halfSpan; degree += 1) {
        const x = centerX + ((degree - rotationDegrees) * ROTATE_PIXELS_PER_DEGREE);
        if (x < 0 || x > width) {
            continue;
        }

        const isMajor = degree % 5 === 0;
        const tickHeight = isMajor ? height * 0.55 : height * 0.3;
        dialContext.lineWidth = isMajor ? 1.5 : 1;
        dialContext.beginPath();
        dialContext.moveTo(x, centerY - (tickHeight / 2));
        dialContext.lineTo(x, centerY + (tickHeight / 2));
        dialContext.stroke();

        if (isMajor) {
            dialContext.fillText(String(degree), x, centerY + (tickHeight / 2) + 12);
        }
    }
}

function beginDialDrag(event) {
    dialDragPointerId = event.pointerId;
    dialDragOriginAngle = rotationDegrees;
    dialDragOriginClientX = event.clientX;
    dialTrackElement.setPointerCapture(event.pointerId);
}

function updateDialDrag(event) {
    if (dialDragPointerId !== event.pointerId || dialDragOriginAngle === null) {
        return;
    }

    const deltaX = event.clientX - dialDragOriginClientX;
    setRotationDegrees(dialDragOriginAngle + (deltaX / ROTATE_PIXELS_PER_DEGREE));
}

function endDialDrag(event) {
    if (dialDragPointerId !== event.pointerId) {
        return;
    }

    if (dialTrackElement.hasPointerCapture(event.pointerId)) {
        dialTrackElement.releasePointerCapture(event.pointerId);
    }
    dialDragPointerId = null;
    dialDragOriginAngle = null;
    dialDragOriginClientX = null;
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
    setHidden(rotateDialElement, !isAspectMode);
    setHidden(actionsElement, !(isDocumentMode || isAspectMode));
    setHidden(autoDetectButton, !isDocumentMode);

    if (!isDocumentMode) {
        hideLoupe();
    }

    if (isAspectMode) {
        drawRotateDial();
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

    const cropState = currentWorkflowMode === ASPECT_RATIO_MODE ? getAspectCropState() : null;
    if (cropState !== null && rotationDegrees !== 0) {
        const pivotX = ((cropState.left + cropState.right) / 2) * scale;
        const pivotY = ((cropState.top + cropState.bottom) / 2) * scale;
        context.save();
        context.translate(pivotX, pivotY);
        context.rotate((rotationDegrees * Math.PI) / 180);
        context.translate(-pivotX, -pivotY);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        context.restore();
    } else {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
    }

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
        rotationDegrees = 0;
        cropCenterX = null;
        cropCenterY = null;
        selectedRatioLabel = null;
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
        rotationDegrees = 0;
        cropCenterX = null;
        cropCenterY = null;
        selectedRatioLabel = null;
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
            zoomPercent = 100;
            marginPercent = 0;
            cropCenterX = null;
            cropCenterY = null;
            selectedRatioLabel = null;
            zoomControl.value = "100";
            marginControl.value = "0";
            setRotationDegrees(0);
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
                marginPercent,
                zoomPercent,
                cropCenterX: cropState.centerX,
                cropCenterY: cropState.centerY,
                rotationDegrees,
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

function beginAspectDrag(cropState, event) {
    aspectDragActive = true;
    aspectDragPointerId = event.pointerId;
    aspectDragOriginCenter = { x: cropState.centerX, y: cropState.centerY };
    aspectDragOriginClient = { x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
    canvas.style.cursor = "grabbing";
}

function finishAspectDrag(event) {
    if (!aspectDragActive || aspectDragPointerId !== event.pointerId) {
        return;
    }

    if (canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
    }
    aspectDragActive = false;
    aspectDragPointerId = null;
    aspectDragOriginCenter = null;
    aspectDragOriginClient = null;
    updateCanvasCursor(event);
}

canvas.addEventListener("pointerdown", (event) => {
    if (!image.naturalWidth) {
        return;
    }

    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        const cropState = getAspectCropState();
        if (cropState === null) {
            return;
        }
        const point = getCanvasPoint(event);
        if (isPointInCropRect(point, cropState)) {
            beginAspectDrag(cropState, event);
        }
        return;
    }

    if (currentWorkflowMode !== DOCUMENT_MODE) {
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
    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        if (!aspectDragActive || aspectDragPointerId !== event.pointerId) {
            updateCanvasCursor(event);
            return;
        }

        const deltaX = (event.clientX - aspectDragOriginClient.x) / Math.max(scale, 0.001);
        const deltaY = (event.clientY - aspectDragOriginClient.y) / Math.max(scale, 0.001);
        cropCenterX = aspectDragOriginCenter.x + deltaX;
        cropCenterY = aspectDragOriginCenter.y + deltaY;
        draw();
        return;
    }

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

canvas.addEventListener("pointerup", (event) => {
    finishDrag(event);
    finishAspectDrag(event);
});
canvas.addEventListener("pointercancel", (event) => {
    finishDrag(event);
    finishAspectDrag(event);
});
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
        zoomPercent = 100;
        marginPercent = 0;
        cropCenterX = null;
        cropCenterY = null;
        selectedRatioLabel = null;
        zoomControl.value = "100";
        marginControl.value = "0";
        setRotationDegrees(0);
        renderAspectControls();
        draw();
        setStatus(currentImageName ? `Reset crop controls for ${currentImageName}` : "Waiting for image...");
    }
});

dialTrackElement.addEventListener("pointerdown", beginDialDrag);
dialTrackElement.addEventListener("pointermove", updateDialDrag);
dialTrackElement.addEventListener("pointerup", endDialDrag);
dialTrackElement.addEventListener("pointercancel", endDialDrag);
dialTrackElement.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
        event.preventDefault();
        setRotationDegrees(rotationDegrees - (event.shiftKey ? 1 : 0.1));
    } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setRotationDegrees(rotationDegrees + (event.shiftKey ? 1 : 0.1));
    }
});

rotateResetButton.addEventListener("click", () => {
    setRotationDegrees(0);
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

ratioOptionsElement.addEventListener("click", (event) => {
    const target = event.target.closest("button[data-ratio-label]");
    if (!target) {
        return;
    }

    const label = target.getAttribute("data-ratio-label");
    selectedRatioLabel = label === "" ? null : label;
    renderAspectControls();
    draw();
});

zoomControl.addEventListener("input", () => {
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
    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        drawRotateDial();
    }
});

image.addEventListener("load", () => {
    draw();
    renderPoints();
    renderAspectControls();
    if (currentWorkflowMode === ASPECT_RATIO_MODE) {
        drawRotateDial();
    }
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