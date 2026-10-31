/*
 * Front-end behaviour for the CV site.
 *
 *  - Global (once per load): theme toggle, toast, mobile nav, nav indicator,
 *    carousel router (pages slide in/out like a carousel on internal links).
 *  - Per page (re-run every time a page panel is swapped in): copy buttons,
 *    experience filter, clickable tags, contact form helpers, scroll reveal.
 */
(() => {
    "use strict";

    const html = document.documentElement;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const STAGE_ID = "main-content";
    const PANEL_SELECTOR = ".page-panel";
    const SLIDE_MS = 650; // keep in sync with --carousel-duration in style.css

    // -------------------------------------------------------------
    // Toast
    // -------------------------------------------------------------
    const toast = document.getElementById("toast");
    let toastTimeout = null;

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("show");
        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => toast.classList.remove("show"), 2500);
    }

    // -------------------------------------------------------------
    // Theme (initial theme is applied by the inline script in <head>)
    // -------------------------------------------------------------
    const themeToggleBtn = document.getElementById("theme-toggle");
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const current = html.getAttribute("data-theme") || "light";
            const next = current === "light" ? "dark" : "light";
            html.setAttribute("data-theme", next);
            try {
                localStorage.setItem("theme", next);
            } catch (err) {
                /* storage unavailable */
            }
            themeToggleBtn.classList.remove("is-spinning");
            void themeToggleBtn.offsetWidth; // restart the animation
            themeToggleBtn.classList.add("is-spinning");
            showToast(`Theme switched to ${next} mode`);
        });
    }

    // -------------------------------------------------------------
    // Mobile navigation
    // -------------------------------------------------------------
    const navToggle = document.getElementById("nav-toggle");
    const navLinksWrap = document.getElementById("nav-links");

    function setMenuOpen(open) {
        if (!navToggle || !navLinksWrap) return;
        navLinksWrap.classList.toggle("open", open);
        navToggle.setAttribute("aria-expanded", String(open));
    }

    if (navToggle && navLinksWrap) {
        navToggle.addEventListener("click", () => setMenuOpen(!navLinksWrap.classList.contains("open")));
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && navLinksWrap.classList.contains("open")) setMenuOpen(false);
        });
    }

    // -------------------------------------------------------------
    // Nav: ordered page list + sliding indicator
    // -------------------------------------------------------------
    const navLinks = Array.from(document.querySelectorAll(".nav-links .nav-link"));
    const pagePaths = navLinks.map((a) => new URL(a.href, location.href).pathname);
    const indicator = document.querySelector(".nav-indicator");

    function pageIndex(pathname) {
        return pagePaths.indexOf(pathname);
    }

    function moveIndicator(animate) {
        if (!indicator) return;
        const active = navLinks.find((a) => a.classList.contains("active"));
        if (!active || active.offsetParent === null) {
            indicator.style.opacity = "0";
            return;
        }
        indicator.classList.toggle("no-transition", !animate);
        indicator.style.opacity = "1";
        indicator.style.transform = `translateX(${active.offsetLeft}px)`;
        indicator.style.width = `${active.offsetWidth}px`;
        if (!animate) {
            void indicator.offsetWidth;
            indicator.classList.remove("no-transition");
        }
    }

    function setActiveNav(pathname) {
        navLinks.forEach((a) => {
            const isActive = new URL(a.href, location.href).pathname === pathname;
            a.classList.toggle("active", isActive);
            if (isActive) a.setAttribute("aria-current", "page");
            else a.removeAttribute("aria-current");
        });
        moveIndicator(true);
    }

    window.addEventListener("resize", () => moveIndicator(false));
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => moveIndicator(false));

    // -------------------------------------------------------------
    // Scroll reveal
    // -------------------------------------------------------------
    const revealObserver =
        "IntersectionObserver" in window
            ? new IntersectionObserver(
                  (entries) => {
                      entries.forEach((entry) => {
                          if (!entry.isIntersecting) return;
                          entry.target.classList.add("is-visible");
                          revealObserver.unobserve(entry.target);
                      });
                  },
                  { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
              )
            : null;

    /**
     * Wire up scroll-reveal for [data-reveal] elements under `root`.
     * With `instantAboveFold`, elements that start inside the viewport are shown
     * immediately without the rise animation – used for carousel slides, where the
     * slide itself is the entrance animation.
     */
    function initReveal(root, { instantAboveFold = false } = {}) {
        const items = Array.from(root.querySelectorAll("[data-reveal]"));
        if (!revealObserver || reduceMotion.matches) {
            items.forEach((el) => el.classList.add("is-visible"));
            return;
        }
        const rootTop = root.getBoundingClientRect ? root.getBoundingClientRect().top : 0;
        const fold = window.innerHeight;
        const perParent = new Map();
        items.forEach((el) => {
            if (instantAboveFold && el.getBoundingClientRect().top - rootTop < fold) {
                el.classList.add("is-visible", "reveal-instant");
                return;
            }
            // Stagger siblings so groups of cards cascade in.
            const n = perParent.get(el.parentElement) || 0;
            perParent.set(el.parentElement, n + 1);
            el.style.setProperty("--reveal-delay", `${Math.min(n, 6) * 70}ms`);
            revealObserver.observe(el);
        });
    }

    // -------------------------------------------------------------
    // Per-page behaviour
    // -------------------------------------------------------------
    function initCopyButtons(root) {
        root.querySelectorAll(".copy-btn").forEach((btn) => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const text = btn.getAttribute("data-copy");
                if (!text) return;
                try {
                    await navigator.clipboard.writeText(text);
                    showToast(`Copied to clipboard: ${text}`);
                } catch (err) {
                    const tmp = document.createElement("input");
                    tmp.value = text;
                    document.body.appendChild(tmp);
                    tmp.select();
                    document.execCommand("copy");
                    document.body.removeChild(tmp);
                    showToast(`Copied: ${text}`);
                }
                btn.classList.remove("is-copied");
                void btn.offsetWidth;
                btn.classList.add("is-copied");
            });
        });
    }

    function initExperienceFilter(root) {
        const filterInput = root.querySelector("#exp-filter-input");
        const items = Array.from(root.querySelectorAll(".timeline-item"));
        const emptyState = root.querySelector("#experience-empty");
        const experienceUrl = document.body.getAttribute("data-experience-url") || "/experience";

        function applyFilter(query) {
            const q = query.trim().toLowerCase();
            let matches = 0;
            items.forEach((item) => {
                const haystack = [
                    item.getAttribute("data-tech") || "",
                    item.getAttribute("data-company") || "",
                    item.getAttribute("data-role") || "",
                    item.textContent.toLowerCase(),
                ].join(" ");
                const isMatch = !q || haystack.includes(q);
                item.style.display = isMatch ? "" : "none";
                if (isMatch) {
                    matches++;
                    item.classList.add("is-visible"); // re-shown items should not wait for the observer
                }
            });
            if (emptyState) emptyState.hidden = matches !== 0;
            return matches;
        }

        function syncQueryParam(query) {
            if (!window.history || !window.history.replaceState) return;
            const url = new URL(window.location.href);
            if (query) url.searchParams.set("q", query);
            else url.searchParams.delete("q");
            window.history.replaceState(history.state, "", url);
        }

        if (filterInput) {
            filterInput.addEventListener("input", (e) => {
                applyFilter(e.target.value);
                syncQueryParam(e.target.value.trim());
            });
            const initial = new URLSearchParams(window.location.search).get("q");
            if (initial) {
                filterInput.value = initial;
                const matches = applyFilter(initial);
                showToast(`Filtered for: "${initial}" (${matches} matching roles)`);
            }
        }

        function activateTag(tag) {
            const name = tag.textContent.trim();
            if (!filterInput) {
                // No filter on this page: roll over to the experience page, pre-filtered.
                navigateTo(`${experienceUrl}?q=${encodeURIComponent(name)}`);
                return;
            }
            if (filterInput.value.toLowerCase() === name.toLowerCase()) {
                filterInput.value = "";
                applyFilter("");
                syncQueryParam("");
                showToast("Cleared filter");
            } else {
                filterInput.value = name;
                const matches = applyFilter(name);
                syncQueryParam(name);
                showToast(`Filtered for: "${name}" (${matches} matching roles)`);
                filterInput.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "nearest" });
            }
        }

        root.querySelectorAll(".tech-tag, .skill-pill").forEach((tag) => {
            tag.style.cursor = "pointer";
            tag.addEventListener("click", () => activateTag(tag));
            tag.addEventListener("keydown", (e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    activateTag(tag);
                }
            });
        });
    }

    function initContactForm(root) {
        const form = root.querySelector("#contact-form");
        if (!form) return;
        const messageField = form.querySelector("#message");
        const counter = form.querySelector("#message-counter");
        const submitBtn = form.querySelector("#contact-submit");

        if (messageField && counter) {
            const max = parseInt(counter.getAttribute("data-max"), 10) || 5000;
            const update = () => {
                const len = messageField.value.length;
                counter.textContent = `${len} / ${max}`;
                counter.classList.toggle("over-limit", len > max);
            };
            messageField.addEventListener("input", update);
            update();
        }

        form.addEventListener("submit", (e) => {
            if (!form.checkValidity()) {
                e.preventDefault();
                form.reportValidity();
                return;
            }
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.classList.add("is-loading");
                const label = submitBtn.querySelector("span");
                if (label) label.textContent = "Sending...";
            }
        });

        const firstInvalid = form.querySelector("[aria-invalid='true']");
        if (firstInvalid) firstInvalid.focus();
    }

    function initActions(root) {
        root.querySelectorAll("[data-action='print']").forEach((btn) => {
            btn.addEventListener("click", () => window.print());
        });
    }

    function initPage(root, options = {}) {
        initActions(root);
        initCopyButtons(root);
        initExperienceFilter(root);
        initContactForm(root);
        initReveal(root, options);
    }

    // -------------------------------------------------------------
    // Carousel router: internal pages slide in like carousel slides
    // -------------------------------------------------------------
    const stage = document.getElementById(STAGE_ID);
    const announcer = document.getElementById("route-announcer");
    const prefetchCache = new Map(); // url -> { html, time }
    const PREFETCH_TTL = 30000;
    let animating = null; // { finish: Function } while a slide is in progress
    let navigationToken = 0;

    function currentPanel() {
        return stage ? stage.querySelector(PANEL_SELECTOR) : null;
    }

    function isInternalPageLink(anchor) {
        if (!anchor || anchor.target || anchor.hasAttribute("download")) return false;
        const url = new URL(anchor.href, location.href);
        if (url.origin !== location.origin) return false;
        if (url.pathname === location.pathname && url.hash && url.search === location.search) return false; // in-page anchor
        return pageIndex(url.pathname) !== -1;
    }

    async function fetchPage(url) {
        const cached = prefetchCache.get(url);
        if (cached && Date.now() - cached.time < PREFETCH_TTL) {
            prefetchCache.delete(url);
            return cached.html;
        }
        const response = await fetch(url, { headers: { "X-Requested-With": "carousel" }, credentials: "same-origin" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
    }

    function prefetch(url) {
        if (prefetchCache.has(url) || url === location.href) return;
        fetchPage(url)
            .then((html) => prefetchCache.set(url, { html, time: Date.now() }))
            .catch(() => {});
    }

    function parsePage(htmlText) {
        const doc = new DOMParser().parseFromString(htmlText, "text/html");
        const panel = doc.querySelector(`#${STAGE_ID} ${PANEL_SELECTOR}`);
        if (!panel) throw new Error("page has no panel");
        const description = doc.querySelector('meta[name="description"]');
        return {
            panel: document.adoptNode(panel),
            title: doc.title,
            description: description ? description.getAttribute("content") : null,
        };
    }

    function applyDocumentMeta(page) {
        document.title = page.title;
        const meta = document.querySelector('meta[name="description"]');
        if (meta && page.description !== null) meta.setAttribute("content", page.description);
    }

    /**
     * Slide `nextPanel` into the stage. direction: 1 = forward (new page comes
     * from the right), -1 = backward, 0 = same page (cross-fade).
     */
    function slideTo(nextPanel, direction, onMounted) {
        if (animating) animating.finish();
        const prevPanel = currentPanel();
        if (!stage || !prevPanel || reduceMotion.matches) {
            if (prevPanel) prevPanel.replaceWith(nextPanel);
            else if (stage) stage.appendChild(nextPanel);
            if (onMounted) onMounted(nextPanel);
            return Promise.resolve();
        }

        return new Promise((resolve) => {
            const startHeight = prevPanel.offsetHeight;
            stage.style.height = `${startHeight}px`;
            stage.classList.add("is-animating");
            stage.dataset.direction = direction > 0 ? "forward" : direction < 0 ? "backward" : "none";

            prevPanel.classList.add("is-leaving");
            nextPanel.classList.add("is-entering", direction > 0 ? "from-right" : direction < 0 ? "from-left" : "from-fade");
            stage.appendChild(nextPanel);
            if (onMounted) onMounted(nextPanel);

            // Measure the incoming page, then let the CSS transitions run.
            const endHeight = nextPanel.offsetHeight;
            void nextPanel.offsetWidth;
            requestAnimationFrame(() => {
                stage.style.height = `${endHeight}px`;
                nextPanel.classList.add("slide-in");
                prevPanel.classList.add(direction > 0 ? "to-left" : direction < 0 ? "to-right" : "to-fade");
            });

            let done = false;
            const finish = () => {
                if (done) return;
                done = true;
                clearTimeout(timer);
                nextPanel.removeEventListener("transitionend", onEnd);
                prevPanel.remove();
                nextPanel.classList.remove("is-entering", "from-right", "from-left", "from-fade", "slide-in");
                stage.classList.remove("is-animating");
                stage.style.height = "";
                delete stage.dataset.direction;
                animating = null;
                resolve();
            };
            const onEnd = (e) => {
                if (e.target === nextPanel && e.propertyName === "transform") finish();
            };
            nextPanel.addEventListener("transitionend", onEnd);
            const timer = setTimeout(finish, SLIDE_MS + 150); // safety net if transitionend never fires
            animating = { finish };
        });
    }

    async function navigateTo(href, { push = true, direction = null, scrollY = 0 } = {}) {
        const url = new URL(href, location.href);
        if (!stage || !currentPanel() || pageIndex(url.pathname) === -1) {
            location.href = url.href;
            return;
        }
        if (push && url.href === location.href) {
            // Already here: just glide back to the top instead of re-fetching.
            window.scrollTo({ top: 0, behavior: reduceMotion.matches ? "auto" : "smooth" });
            setMenuOpen(false);
            return;
        }
        const token = ++navigationToken;
        const fromIndex = pageIndex(location.pathname);
        const toIndex = pageIndex(url.pathname);
        const dir = direction !== null ? direction : Math.sign(toIndex - fromIndex);

        let page;
        try {
            page = parsePage(await fetchPage(url.href));
        } catch (err) {
            location.href = url.href; // graceful fallback to a normal navigation
            return;
        }
        if (token !== navigationToken) return; // a newer navigation superseded this one

        setMenuOpen(false);
        if (push) {
            // Remember where we were so Back can restore the scroll position.
            history.replaceState({ ...(history.state || {}), carousel: true, scrollY: window.scrollY }, "", location.href);
            history.pushState({ carousel: true, scrollY: 0 }, "", url.href);
        }
        applyDocumentMeta(page);
        setActiveNav(url.pathname);
        window.scrollTo({ top: scrollY, behavior: "auto" });

        const panel = page.panel;
        await slideTo(panel, dir, (mounted) => initPage(mounted, { instantAboveFold: true }));
        if (scrollY) window.scrollTo({ top: scrollY, behavior: "auto" });
        stage.focus({ preventScroll: true });
        if (announcer) announcer.textContent = `Navigated to ${document.title}`;
        stage.dispatchEvent(new CustomEvent("carousel:navigated", { bubbles: true, detail: { path: url.pathname } }));
    }

    function onDocumentClick(e) {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const anchor = e.target.closest("a[href]");
        if (!anchor || !isInternalPageLink(anchor)) return;
        if (reduceMotion.matches) return; // let the browser do a plain navigation
        e.preventDefault();
        navigateTo(anchor.href);
    }

    function onPopState(e) {
        if (!stage || reduceMotion.matches) return;
        const scrollY = e.state && typeof e.state.scrollY === "number" ? e.state.scrollY : 0;
        navigateTo(location.href, { push: false, scrollY });
    }

    // Touch swipe between neighbouring pages (carousel gesture).
    let touchStart = null;
    function onTouchStart(e) {
        if (e.touches.length !== 1) return;
        touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, target: e.target };
    }
    function onTouchEnd(e) {
        if (!touchStart || reduceMotion.matches) return;
        const dx = e.changedTouches[0].clientX - touchStart.x;
        const dy = e.changedTouches[0].clientY - touchStart.y;
        const fromField = touchStart.target.closest("input, textarea, select");
        touchStart = null;
        if (fromField || Math.abs(dx) < 90 || Math.abs(dy) > Math.abs(dx) * 0.6) return;
        const index = pageIndex(location.pathname);
        const next = dx < 0 ? index + 1 : index - 1;
        if (index === -1 || next < 0 || next >= pagePaths.length) return;
        navigateTo(pagePaths[next], { direction: dx < 0 ? 1 : -1 });
    }

    if (stage && currentPanel() && window.fetch && window.DOMParser && "pushState" in history) {
        history.scrollRestoration = "manual";
        history.replaceState({ carousel: true, scrollY: window.scrollY }, "", location.href);
        document.addEventListener("click", onDocumentClick);
        window.addEventListener("popstate", onPopState);
        document.addEventListener("touchstart", onTouchStart, { passive: true });
        document.addEventListener("touchend", onTouchEnd, { passive: true });
        navLinks.forEach((a) => {
            a.addEventListener("mouseenter", () => prefetch(a.href), { passive: true });
            a.addEventListener("focus", () => prefetch(a.href), { passive: true });
        });
    }

    // -------------------------------------------------------------
    // Boot
    // -------------------------------------------------------------
    window.__animReady = true;
    const initialPanel = currentPanel();
    initPage(initialPanel || document);
    moveIndicator(false);
    html.classList.add("page-loaded");

    // Small public surface for tests and the console.
    window.resumeApp = { navigateTo, showToast, pagePaths };
})();
