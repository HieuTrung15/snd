(() => {
	const TITLE = "TẬP ĐOÀN DỆT MAY VIỆT NAM";
	const SUB_TITLE = "";

	const removeOldBrandText = () => {
		document.querySelectorAll(".vnt-brand-text").forEach((el) => el.remove());
	};

	const ensureSearchTitle = () => {
		const navbar =
			document.querySelector("header.navbar") ||
			document.querySelector(".navbar");
		if (!navbar) return;

		let title = document.getElementById("vnt-search-title");
		if (!title) {
			title = document.createElement("div");
			title.id = "vnt-search-title";
			title.className = "vnt-search-title";
			title.innerHTML = `
				<div class="vnt-search-title-line">${TITLE}</div>
				<div class="vnt-search-subtitle">${SUB_TITLE}</div>
			`;
			navbar.appendChild(title);
		} else if (title.parentElement !== navbar) {
			navbar.appendChild(title);
		}
	};

	const init = () => {
		removeOldBrandText();
		setTimeout(() => {
			removeOldBrandText();
			ensureSearchTitle();
		}, 0);
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}

	if (window?.frappe?.router?.on) {
		window.frappe.router.on("change", () => init());
	}
})();
