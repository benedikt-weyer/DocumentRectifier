const canvas = document.getElementById("canvas");
const context = canvas.getContext("2d");
const loupeElement = document.getElementById("loupe");
const loupeCanvas = document.getElementById("loupe-canvas");
const loupeContext = loupeCanvas.getContext("2d");
const statusElement = document.getElementById("status");
const progressLabelElement = document.getElementById("progress-label");
const progressRemainingElement = document.getElementById("progress-remaining");
const progressTrackElement = document.getElementById("progress-track");
const imageNameElement = document.getElementById("image-name");
const pointsElement = document.getElementById("points");
const saveButton = document.getElementById("save");
const autoDetectButton = document.getElementById("auto-detect");
const image = new Image();

const HANDLE_RADIUS = 12;
const HANDLE_HIT_PADDING = 10;
const LOUPE_ZOOM = 4;
const LOUPE_OFFSET_X = 24;
const LOUPE_OFFSET_Y = 24;
const DRAG_DAMPING = 0.35;

let currentVersion = null;
let currentImageName = null;
let scale = 1;
let points = [];
let dragIndex = null;
let activePointerId = null;
let dragOriginPoint = null;
let dragOriginClient = null;

function setStatus(text) {
    statusElement.textContent = text;
}

function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
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
    if (!image.naturalWidth || !image.naturalHeight) {
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

function renderPoints() {
    if (points.length === 0) {
        pointsElement.innerHTML = "<span>No points selected yet.</span>";
    } else {
        pointsElement.innerHTML = points
            .map((point, index) => `<span><strong>${index + 1}.</strong> (${Math.round(point.x)}, ${Math.round(point.y)})</span>`)
            .join("");
    }
    saveButton.disabled = points.length !== 4;
    autoDetectButton.disabled = !image.naturalWidth;
}

async function autoDetectCorners() {
    if (!image.naturalWidth) {
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
        setStatus(error.message);
    } finally {
        renderPoints();
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

function draw() {
    if (!image.naturalWidth || !image.naturalHeight) {
        return;
    }

    const maxWidth = Math.max(window.innerWidth - 440, 320);
    const maxHeight = Math.max(window.innerHeight - 220, 320);
    scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
    canvas.width = Math.round(image.naturalWidth * scale);
    canvas.height = Math.round(image.naturalHeight * scale);

    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

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

async function fetchState() {
    const response = await fetch("/state", { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`State request failed: ${response.status}`);
    }

    const state = await response.json();
    renderProgress(state);
    if (!state.hasImage) {
        currentVersion = null;
        currentImageName = null;
        points = [];
        dragIndex = null;
        activePointerId = null;
        hideLoupe();
        renderPoints();
        imageNameElement.textContent = state.message;
        setStatus(state.message);
        context.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }

    if (state.version !== currentVersion) {
        currentVersion = state.version;
        currentImageName = state.imageName;
        points = [];
        dragIndex = null;
        activePointerId = null;
        hideLoupe();
        renderPoints();
        imageNameElement.textContent = state.imageName;
        setStatus(`Select corners for ${state.imageName}`);
        image.src = `/image?v=${state.version}`;
    }
}

async function submit(action) {
    if (action === "save" && points.length !== 4) {
        setStatus("Select exactly four points before saving.");
        return;
    }

    saveButton.disabled = true;
    const response = await fetch("/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, points }),
    });

    if (!response.ok) {
        const errorText = await response.text();
        setStatus(errorText || `Submission failed: ${response.status}`);
        renderPoints();
        return;
    }

    setStatus(action === "save" ? "Saved. Waiting for next image..." : "Advancing...");
}

canvas.addEventListener("pointerdown", (event) => {
    if (!image.naturalWidth) {
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
        x: clamp(dragOriginPoint.x + deltaX * DRAG_DAMPING, 0, Math.max(image.naturalWidth - 1, 0)),
        y: clamp(dragOriginPoint.y + deltaY * DRAG_DAMPING, 0, Math.max(image.naturalHeight - 1, 0)),
    };
    renderPoints();
    draw();
    drawLoupe(points[dragIndex], event.clientX, event.clientY);
});

function finishDrag(event) {
    if (dragIndex === null || activePointerId !== event.pointerId) {
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
    if (dragIndex === null) {
        canvas.style.cursor = points.length < 4 ? "crosshair" : "default";
        hideLoupe();
        return;
    }

    drawLoupe(points[dragIndex], event.clientX, event.clientY);
});

document.getElementById("reset").addEventListener("click", () => {
    points = [];
    dragIndex = null;
    activePointerId = null;
    dragOriginPoint = null;
    dragOriginClient = null;
    hideLoupe();
    renderPoints();
    draw();
    setStatus(currentImageName ? `Reset points for ${currentImageName}` : "Waiting for image...");
});
document.getElementById("save").addEventListener("click", () => submit("save"));
autoDetectButton.addEventListener("click", autoDetectCorners);
document.getElementById("skip").addEventListener("click", () => submit("skip"));
document.getElementById("quit").addEventListener("click", () => submit("quit"));
window.addEventListener("resize", () => {
    draw();
    hideLoupe();
});
image.addEventListener("load", () => {
    draw();
    renderPoints();
});

renderPoints();
setInterval(() => {
    void refreshState();
}, 600);

async function refreshState() {
    try {
        await fetchState();
    } catch (error) {
        setStatus(error.message);
    }
}

await refreshState();