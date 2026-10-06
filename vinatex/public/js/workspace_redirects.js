// (() => {
// 	const WORKSPACE_REDIRECTS = {
// 		// Workspace: "Bảng tin chỉ đạo điều hành"
// 		"bang-tin-chi-dao-dieu-hanh": "https://ihrm.vinatex.com.vn/leadership-spa",
// 		"bảng tin chỉ đạo điều hành": "https://ihrm.vinatex.com.vn/leadership-spa",
// 		"bảng-tin-chỉ-đạo-điều-hành": "https://ihrm.vinatex.com.vn/leadership-spa",
// 		"bảng_tin_chỉ_đạo_điều_hành": "https://ihrm.vinatex.com.vn/leadership-spa",
// 	};

// 	const QUICK_PATH_SLUGS = [
// 		"bang-tin-chi-dao-dieu-hanh",
// 		"bảng-tin-chỉ-đạo-điều-hành",
// 		"bảng_tin_chỉ_đạo_điều_hành",
// 	];
// 	const slugify = (value) => {
// 		return (value || "")
// 			.toString()
// 			.normalize("NFD")
// 			.replace(/[\u0300-\u036f]/g, "")
// 			.replace(/[^a-zA-Z0-9]+/g, "-")
// 			.replace(/^-+|-+$/g, "")
// 			.toLowerCase();
// 	};

// 	const getWorkspaceSlug = () => {
// 		const route = (window.frappe?.get_route && window.frappe.get_route()) || [];
// 		const primary = (route[0] || "").toString();
// 		const secondary = (route[1] || "").toString();

// 		// New desk keeps workspace slugs at route[0]; old desk uses /workspaces/<slug>
// 		if (primary.toLowerCase() === "workspaces") return secondary;

// 		// Try to read from the URL path after /app/
// 		const parts = decodeURIComponent(window.location.pathname || "")
// 			.split("/")
// 			.filter(Boolean);
// 		const appIdx = parts.indexOf("app");
// 		if (appIdx >= 0 && parts[appIdx + 1]) {
// 			// Last segment is the workspace slug when navigated via sidebar
// 			return parts[parts.length - 1];
// 		}

// 		return primary;
// 	};

// 	const maybeRedirect = () => {
// 		// Fast path: match by URL path immediately (no frappe)
// 		const pathname = decodeURIComponent(window.location.pathname || "").toLowerCase();
// 		const quickMatch = QUICK_PATH_SLUGS.find((slug) => pathname.includes(slug));
// 		if (quickMatch) {
// 			const quickTarget = WORKSPACE_REDIRECTS[quickMatch];
// 			if (quickTarget && window.location.href !== quickTarget) {
// 				window.location.replace(quickTarget);
// 				return;
// 			}
// 		}

// 		const raw = getWorkspaceSlug();
// 		if (!raw) return;

// 		const slug = slugify(raw);
// 		const targetUrl =
// 			WORKSPACE_REDIRECTS[raw.toLowerCase()] || WORKSPACE_REDIRECTS[slug];

// 		if (targetUrl && window.location.href !== targetUrl) {
// 			window.location.replace(targetUrl);
// 		}
// 	};

// 	const init = () => maybeRedirect();

// 	if (document.readyState === "loading") {
// 		document.addEventListener("DOMContentLoaded", init);
// 	} else {
// 		init();
// 	}

// 	if (window?.frappe?.router?.on) {
// 		window.frappe.router.on("change", () => maybeRedirect());
// 	}
// })();
