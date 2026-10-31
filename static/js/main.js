document.addEventListener("DOMContentLoaded", () => {
    const htmlElement = document.documentElement;

    // -------------------------------------------------------------
    // 1. Toast Notifications
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
    // 2. Theme Management (Dark / Light Mode)
    //    The initial theme is applied by an inline script in <head>.
    // -------------------------------------------------------------
    const themeToggleBtn = document.getElementById("theme-toggle");
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const currentTheme = htmlElement.getAttribute("data-theme") || "light";
            const newTheme = currentTheme === "light" ? "dark" : "light";
            htmlElement.setAttribute("data-theme", newTheme);
            try {
                localStorage.setItem("theme", newTheme);
            } catch (err) {
                /* storage unavailable */
            }
            showToast(`Theme switched to ${newTheme} mode`);
        });
    }

    // -------------------------------------------------------------
    // 3. Mobile navigation toggle
    // -------------------------------------------------------------
    const navToggle = document.getElementById("nav-toggle");
    const navLinks = document.getElementById("nav-links");
    if (navToggle && navLinks) {
        navToggle.addEventListener("click", () => {
            const isOpen = navLinks.classList.toggle("open");
            navToggle.setAttribute("aria-expanded", String(isOpen));
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && navLinks.classList.contains("open")) {
                navLinks.classList.remove("open");
                navToggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    // -------------------------------------------------------------
    // 4. Copy to Clipboard
    // -------------------------------------------------------------
    document.querySelectorAll(".copy-btn").forEach((btn) => {
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
    // 5. Experience Filter / Search
    // -------------------------------------------------------------
    const filterInput = document.getElementById("exp-filter-input");
    const timelineItems = document.querySelectorAll(".timeline-item");
    const emptyState = document.getElementById("experience-empty");
    const experienceUrl = document.body.getAttribute("data-experience-url") || "/experience";

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

            item.style.display = isMatch ? "" : "none";
            if (isMatch) matchCount++;
        });

        if (emptyState) emptyState.hidden = matchCount !== 0;
        return matchCount;
    }

    function syncQueryParam(query) {
        if (!window.history || !window.history.replaceState) return;
        const url = new URL(window.location.href);
        if (query) {
            url.searchParams.set("q", query);
        } else {
            url.searchParams.delete("q");
        }
        window.history.replaceState({}, "", url);
    }

    if (filterInput) {
        filterInput.addEventListener("input", (e) => {
            applyFilter(e.target.value);
            syncQueryParam(e.target.value.trim());
        });

        // Pre-fill from ?q= so other pages can deep-link into a filtered view.
        const initialQuery = new URLSearchParams(window.location.search).get("q");
        if (initialQuery) {
            filterInput.value = initialQuery;
            const matches = applyFilter(initialQuery);
            showToast(`Filtered for: "${initialQuery}" (${matches} matching roles)`);
        }
    }

    // Clicking a skill pill or tech tag filters the experience list. If the
    // current page has no filter box, jump to the experience page instead.
    function handleTagActivate(tag) {
        const tagName = tag.textContent.trim();
        if (!filterInput) {
            window.location.href = `${experienceUrl}?q=${encodeURIComponent(tagName)}`;
            return;
        }
        if (filterInput.value.toLowerCase() === tagName.toLowerCase()) {
            filterInput.value = "";
            applyFilter("");
            syncQueryParam("");
            showToast("Cleared filter");
        } else {
            filterInput.value = tagName;
            const matches = applyFilter(tagName);
            syncQueryParam(tagName);
            showToast(`Filtered for: "${tagName}" (${matches} matching roles)`);
            filterInput.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }

    document.querySelectorAll(".tech-tag, .skill-pill").forEach((tag) => {
        tag.style.cursor = "pointer";
        tag.addEventListener("click", () => handleTagActivate(tag));
        tag.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleTagActivate(tag);
            }
        });
    });

    // -------------------------------------------------------------
    // 6. Contact form enhancements
    // -------------------------------------------------------------
    const contactForm = document.getElementById("contact-form");
    if (contactForm) {
        const messageField = document.getElementById("message");
        const counter = document.getElementById("message-counter");
        const submitBtn = document.getElementById("contact-submit");

        if (messageField && counter) {
            const max = parseInt(counter.getAttribute("data-max"), 10) || 5000;
            const updateCounter = () => {
                const len = messageField.value.length;
                counter.textContent = `${len} / ${max}`;
                counter.classList.toggle("over-limit", len > max);
            };
            messageField.addEventListener("input", updateCounter);
            updateCounter();
        }

        contactForm.addEventListener("submit", (e) => {
            // Let the browser's built-in validation run first.
            if (!contactForm.checkValidity()) {
                e.preventDefault();
                contactForm.reportValidity();
                return;
            }
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.classList.add("is-loading");
                const label = submitBtn.querySelector("span");
                if (label) label.textContent = "Sending...";
            }
        });

        // Focus the first invalid field when the server reports errors.
        const firstInvalid = contactForm.querySelector("[aria-invalid='true']");
        if (firstInvalid) firstInvalid.focus();
    }
});
