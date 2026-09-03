document.addEventListener("DOMContentLoaded", () => {
    const statusBadge = document.getElementById("statusBadge");
    const statusText = document.getElementById("statusText");
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

    // Secret Admin Click Counter
    let adminClickCount = 0;
    let adminClickTimer = null;

    async function checkStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            
            if (data.cooldown_total) {
                totalCooldownSeconds = data.cooldown_total;
            }

            if (data.authorized) {
                statusBadge.className = "status-badge status-online";
                statusText.textContent = `Connected (@${data.bot})`;
            } else {
                statusBadge.className = "status-badge status-offline";
                statusText.textContent = "Auth Required";
                showError("Telegram account not authorized. Run 'python setup_session.py' in the terminal.");
            }

            if (data.cooldown_remaining > 0) {
                startCooldown(data.cooldown_remaining, totalCooldownSeconds);
            }
        } catch (err) {
            statusBadge.className = "status-badge status-offline";
            statusText.textContent = "Server Offline";
            showError("Could not connect to backend server.");
        }
    }

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

    // Secret 10-Click Reset on Timer
    function handleSecretAdminReset() {
        adminClickCount++;
        clearTimeout(adminClickTimer);
        adminClickTimer = setTimeout(() => {
            adminClickCount = 0;
        }, 3000); // 10 clicks must be within 3 seconds

        if (adminClickCount >= 10) {
            adminClickCount = 0;
            // Call server to reset cooldown timestamp
            fetch("/api/admin/reset-cooldown", { method: "POST" })
                .then(r => r.json())
                .then(() => {
                    if (cooldownInterval) clearInterval(cooldownInterval);
                    localStorage.removeItem("cooldown_end_time");
                    cooldownContainer.classList.add("hidden");
                    searchBtn.disabled = false;
                })
                .catch(err => console.error(err));
        }
    }

    // Attach secret listener to both timer and the cooldown container
    cooldownTimer.addEventListener("click", handleSecretAdminReset);
    cooldownContainer.addEventListener("click", handleSecretAdminReset);

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
                body: JSON.stringify({ query })
            });

            const data = await res.json();

            if (res.status === 429) {
                showError(data.message || "Rate limit active. Please wait.");
                if (data.remaining_seconds) {
                    startCooldown(data.remaining_seconds, totalCooldownSeconds);
                }
                return;
            }

            if (!res.ok) {
                throw new Error(data.detail || data.message || "Request failed");
            }

            queryLabel.textContent = `Query: ${data.query}`;
            resultOutput.textContent = data.result || "No text returned by bot.";
            resultSection.classList.remove("hidden");

            if (data.cooldown_seconds) {
                startCooldown(data.cooldown_seconds, data.cooldown_seconds);
            }

        } catch (err) {
            showError(err.message || "Failed to query the bot.");
        } finally {
            searchBtn.classList.remove("loading");
            if (!cooldownInterval || localStorage.getItem("cooldown_end_time") === null) {
                searchBtn.disabled = false;
            }
        }
    });

    copyBtn.addEventListener("click", async () => {
        const text = resultOutput.textContent;
        if (!text) return;
        try {
            await navigator.clipboard.writeText(text);
            copyBtnText.textContent = "Copied!";
            setTimeout(() => {
                copyBtnText.textContent = "Copy";
            }, 2000);
        } catch (err) {
            console.error("Failed to copy", err);
        }
    });

    checkStoredCooldown();
    checkStatus();
});
