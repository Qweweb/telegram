document.addEventListener("DOMContentLoaded", () => {
    // --- 1. Authentic Dense Matrix Digital Rain Animation (Image 3 Style) ---
    const canvas = document.getElementById("matrixCanvas");
    const ctx = canvas.getContext("2d");

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    // Matrix characters (0, 1, binary, and digital glyphs)
    const chars = "01010101010110010101010101010101010111001010101019876543210#@&*%$";
    const fontSize = 16;
    let columns = Math.floor(canvas.width / fontSize);
    let drops = Array(columns).fill(1);

    window.addEventListener("resize", () => {
        columns = Math.floor(canvas.width / fontSize);
        drops = Array(columns).fill(1);
    });

    function drawMatrix() {
        // Deep translucent black trail
        ctx.fillStyle = "rgba(0, 0, 0, 0.06)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.font = "bold " + fontSize + "px 'JetBrains Mono', monospace";

        for (let i = 0; i < drops.length; i++) {
            const char = chars.charAt(Math.floor(Math.random() * chars.length));
            const x = i * fontSize;
            const y = drops[i] * fontSize;

            // Random bright head character
            if (Math.random() > 0.88) {
                ctx.fillStyle = "#ffffff";
                ctx.shadowColor = "#00ff41";
                ctx.shadowBlur = 8;
            } else {
                ctx.fillStyle = "#00ff41";
                ctx.shadowBlur = 0;
            }

            ctx.fillText(char, x, y);

            if (y > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
    }
    setInterval(drawMatrix, 33);

    // --- 2. Persistent Hardware Device ID ---
    function getDeviceIdentifier() {
        if (window.AndroidBridge && typeof window.AndroidBridge.getDeviceId === "function") {
            try {
                const nativeId = window.AndroidBridge.getDeviceId();
                if (nativeId && nativeId.trim()) {
                    return "hw_" + nativeId.trim();
                }
            } catch (e) {}
        }

        let storedId = localStorage.getItem("dev_fingerprint_id");
        if (!storedId) {
            const screenInfo = `${screen.width}x${screen.height}_${screen.colorDepth}_${navigator.hardwareConcurrency || 4}`;
            const randomPart = Math.random().toString(36).substring(2, 12) + Date.now().toString(36);
            storedId = `dev_${screenInfo}_${randomPart}`;
            localStorage.setItem("dev_fingerprint_id", storedId);
        }
        return storedId;
    }

    const currentDeviceId = getDeviceIdentifier();

    // --- 3. DOM Elements ---
    const statusBadge = document.getElementById("statusBadge");
    const statusText = document.getElementById("statusText");
    const quotaText = document.getElementById("quotaText");
    const searchForm = document.getElementById("searchForm");
    const queryInput = document.getElementById("queryInput");
    const clearBtn = document.getElementById("clearBtn");
    const searchBtn = document.getElementById("searchBtn");
    const cooldownContainer = document.getElementById("cooldownContainer");
    const cooldownTimer = document.getElementById("cooldownTimer");
    const progressBar = document.getElementById("progressBar");
    const errorBanner = document.getElementById("errorBanner");
    const errorMessage = document.getElementById("errorMessage");
    const resultSection = document.getElementById("resultSection");
    const queryLabel = document.getElementById("queryLabel");
    const resultOutput = document.getElementById("resultOutput");
    const copyBtn = document.getElementById("copyBtn");
    const copyBtnText = document.getElementById("copyBtnText");

    let cooldownInterval = null;
    let totalCooldownSeconds = 600;

    // --- 4. Secret Admin 10-Tap Reset ---
    let adminClickCount = 0;
    let adminClickTimer = null;

    function handleSecretAdminReset() {
        adminClickCount++;
        clearTimeout(adminClickTimer);
        adminClickTimer = setTimeout(() => {
            adminClickCount = 0;
        }, 3000);

        if (adminClickCount >= 10) {
            adminClickCount = 0;
            fetch("/api/admin/reset-cooldown", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ device_id: currentDeviceId })
            })
            .then(r => r.json())
            .then(data => {
                if (cooldownInterval) clearInterval(cooldownInterval);
                localStorage.removeItem("cooldown_end_time");
                cooldownContainer.classList.add("hidden");
                searchBtn.disabled = false;
                checkStatus();
            })
            .catch(err => console.error(err));
        }
    }

    cooldownTimer.addEventListener("click", handleSecretAdminReset);
    cooldownContainer.addEventListener("click", handleSecretAdminReset);
    statusBadge.addEventListener("click", handleSecretAdminReset);

    // --- 5. Status & Quota Verification ---
    async function checkStatus() {
        try {
            const res = await fetch(`/api/status?device_id=${encodeURIComponent(currentDeviceId)}`);
            const data = await res.json();
            
            if (data.cooldown_total) {
                totalCooldownSeconds = data.cooldown_total;
            }

            // Clean 100% Anonymous Connected Label (No Bot Name)
            if (data.authorized) {
                statusBadge.className = "status-badge status-online";
                statusText.textContent = "CONNECTED";
            } else {
                statusBadge.className = "status-badge status-offline";
                statusText.textContent = "OFFLINE";
            }

            // Quota Badge
            if (data.searches_left !== undefined) {
                quotaText.textContent = `${data.searches_left}/${data.max_searches || 7}`;
            }

            // Device Lockout Check
            if (data.is_locked) {
                searchBtn.disabled = true;
                showError(`DEVICE ACCESS LOCKED: ${data.max_searches}/${data.max_searches} searches used.`);
                return;
            }

            if (data.cooldown_remaining > 0) {
                startCooldown(data.cooldown_remaining, totalCooldownSeconds);
            }
        } catch (err) {
            statusBadge.className = "status-badge status-offline";
            statusText.textContent = "OFFLINE";
        }
    }

    // --- 6. Cooldown Manager ---
    function startCooldown(remainingSeconds, totalSeconds = 600) {
        if (cooldownInterval) clearInterval(cooldownInterval);
        
        const targetEndTime = Date.now() + remainingSeconds * 1000;
        localStorage.setItem("cooldown_end_time", targetEndTime);
        localStorage.setItem("cooldown_total", totalSeconds);

        cooldownContainer.classList.remove("hidden");
        searchBtn.disabled = true;

        function updateTimer() {
            const now = Date.now();
            const leftMs = targetEndTime - now;
            
            if (leftMs <= 0) {
                clearInterval(cooldownInterval);
                cooldownContainer.classList.add("hidden");
                searchBtn.disabled = false;
                localStorage.removeItem("cooldown_end_time");
                return;
            }

            const leftSecs = Math.ceil(leftMs / 1000);
            const mins = Math.floor(leftSecs / 60);
            const secs = leftSecs % 60;
            
            cooldownTimer.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            
            const progressPercent = (leftSecs / totalSeconds) * 100;
            progressBar.style.width = `${progressPercent}%`;
        }

        updateTimer();
        cooldownInterval = setInterval(updateTimer, 1000);
    }

    function checkStoredCooldown() {
        const storedEndTime = localStorage.getItem("cooldown_end_time");
        const storedTotal = localStorage.getItem("cooldown_total") || 600;
        if (storedEndTime) {
            const remaining = Math.ceil((parseInt(storedEndTime, 10) - Date.now()) / 1000);
            if (remaining > 0) {
                startCooldown(remaining, parseInt(storedTotal, 10));
            } else {
                localStorage.removeItem("cooldown_end_time");
            }
        }
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorBanner.classList.remove("hidden");
    }

    function hideError() {
        errorBanner.classList.add("hidden");
    }

    queryInput.addEventListener("input", () => {
        clearBtn.style.display = queryInput.value.length > 0 ? "block" : "none";
        hideError();
    });

    clearBtn.addEventListener("click", () => {
        queryInput.value = "";
        clearBtn.style.display = "none";
        queryInput.focus();
    });

    // --- 7. Search Execution ---
    searchForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        hideError();
        resultSection.classList.add("hidden");
        searchBtn.classList.add("loading");
        searchBtn.disabled = true;

        try {
            const res = await fetch("/api/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, device_id: currentDeviceId })
            });

            const data = await res.json();

            if (res.status === 403) {
                showError(data.message || "Quota limit reached for this device (7/7).");
                quotaText.textContent = "0/7";
                return;
            }

            if (res.status === 429) {
                showError(data.message || "Cooldown active. Please wait.");
                if (data.remaining_seconds) {
                    startCooldown(data.remaining_seconds, totalCooldownSeconds);
                }
                if (data.searches_left !== undefined) {
                    quotaText.textContent = `${data.searches_left}/7`;
                }
                return;
            }

            if (!res.ok) {
                throw new Error(data.detail || data.message || "Request failed");
            }

            if (data.searches_left !== undefined) {
                quotaText.textContent = `${data.searches_left}/${data.max_searches || 7}`;
            }

            // Display Result
            queryLabel.textContent = `TARGET: ${data.query}`;
            resultOutput.textContent = data.result || "No data returned.";
            resultSection.classList.remove("hidden");

            if (data.cooldown_seconds) {
                startCooldown(data.cooldown_seconds, data.cooldown_seconds);
            }

        } catch (err) {
            showError(err.message || "Failed to query database.");
        } finally {
            searchBtn.classList.remove("loading");
            if (!cooldownInterval || localStorage.getItem("cooldown_end_time") === null) {
                searchBtn.disabled = false;
            }
        }
    });

    // Copy Result
    copyBtn.addEventListener("click", async () => {
        const text = resultOutput.textContent;
        if (!text) return;
        try {
            await navigator.clipboard.writeText(text);
            copyBtnText.textContent = "COPIED";
            setTimeout(() => {
                copyBtnText.textContent = "COPY";
            }, 2000);
        } catch (err) {}
    });

    checkStoredCooldown();
    checkStatus();
});
