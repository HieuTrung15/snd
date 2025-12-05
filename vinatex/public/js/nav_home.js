
(() => {
    const ensureBrandNavHome = () => {
		const brands = Array.from(
			document.querySelectorAll("header.navbar .navbar-brand, .navbar .navbar-brand, .navbar-home")
		);
		if (!brands.length) return;
		brands.forEach((brand) => {
			brand.style.cursor = "pointer";
			if (brand.getAttribute("href") !== "/app/home") {
				brand.setAttribute("href", "/app/home");
			}
			// Đặt data-flag để không bind trùng
			if (!brand.dataset.vntNavHome) {
				brand.addEventListener("click", (e) => {
					e.preventDefault();
					e.stopPropagation();
					window.location.href = "/app/home";
				});
				brand.dataset.vntNavHome = "1";
			}
		});
	};

    const init = () => {
        ensureBrandNavHome();
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