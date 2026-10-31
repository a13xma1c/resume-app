document.addEventListener("DOMContentLoaded", () => {
    // -------------------------------------------------------------
    // 1. Theme Management (Dark / Light Mode)
    // -------------------------------------------------------------
    const themeToggleBtn = document.getElementById("theme-toggle");
    const htmlElement = document.documentElement;

    const savedTheme = localStorage.getItem("theme");
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    if (savedTheme) {
        htmlElement.setAttribute("data-theme", savedTheme);
    } else if (systemPrefersDark) {
        htmlElement.setAttribute("data-theme", "dark");
    }

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const currentTheme = htmlElement.getAttribute("data-theme") || "light";
            const newTheme = currentTheme === "light" ? "dark" : "light";
            htmlElement.setAttribute("data-theme", newTheme);
            localStorage.setItem("theme", newTheme);
            showToast(`Theme switched to ${newTheme} mode`);
        });
    }

    // -------------------------------------------------------------
    // 2. Toast Notifications
    // -------------------------------------------------------------
    const toast = document.getElementById("toast");
    let toastTimeout = null;

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("show");

        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => {
            toast.classList.remove("show");
        }, 2500);
    }

    // -------------------------------------------------------------
    // 3. Copy to Clipboard
    // -------------------------------------------------------------
    const copyButtons = document.querySelectorAll(".copy-btn");
    copyButtons.forEach((btn) => {
        btn.addEventListener("click", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const textToCopy = btn.getAttribute("data-copy");
            if (!textToCopy) return;

            try {
                await navigator.clipboard.writeText(textToCopy);
                showToast(`Copied to clipboard: ${textToCopy}`);
            } catch (err) {
                // Fallback for environments where navigator.clipboard might be restricted
                const tempInput = document.createElement("input");
                tempInput.value = textToCopy;
                document.body.appendChild(tempInput);
                tempInput.select();
                document.execCommand("copy");
                document.body.removeChild(tempInput);
                showToast(`Copied: ${textToCopy}`);
            }
        });
    });

    // -------------------------------------------------------------
    // 4. Experience Filter / Search
    // -------------------------------------------------------------
    const filterInput = document.getElementById("exp-filter-input");
    const timelineItems = document.querySelectorAll(".timeline-item");

    function applyFilter(query) {
        const cleanQuery = query.trim().toLowerCase();
        let matchCount = 0;

        timelineItems.forEach((item) => {
            const tech = item.getAttribute("data-tech") || "";
            const company = item.getAttribute("data-company") || "";
            const role = item.getAttribute("data-role") || "";
            const text = item.textContent.toLowerCase();

            const isMatch = !cleanQuery ||
                tech.includes(cleanQuery) ||
                company.includes(cleanQuery) ||
                role.includes(cleanQuery) ||
                text.includes(cleanQuery);

            if (isMatch) {
                item.style.display = "";
                matchCount++;
            } else {
                item.style.display = "none";
            }
        });

        return matchCount;
    }

    if (filterInput) {
        filterInput.addEventListener("input", (e) => {
            applyFilter(e.target.value);
        });
    }

    // Clicking on skill pills or tech tags filters experience
    const interactiveTags = document.querySelectorAll(".tech-tag, .skill-pill");
    interactiveTags.forEach((tag) => {
        tag.style.cursor = "pointer";
        tag.addEventListener("click", () => {
            const tagName = tag.textContent.trim();
            if (filterInput) {
                if (filterInput.value.toLowerCase() === tagName.toLowerCase()) {
                    filterInput.value = "";
                    applyFilter("");
                    showToast("Cleared filter");
                } else {
                    filterInput.value = tagName;
                    const matches = applyFilter(tagName);
                    showToast(`Filtered for: "${tagName}" (${matches} matching roles)`);
                    filterInput.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }
            }
        });
    });
});
