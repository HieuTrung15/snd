(() => {
	const DEFAULT_SALUTATION = "anh/chị";
	let userProfilePromise;

	const getUserFullName = () => {
		const frappeObj = window?.frappe;
		if (!frappeObj) return "";

		// Prefer session fullname, otherwise fall back to boot info
		if (frappeObj.session?.user_fullname) return frappeObj.session.user_fullname;

		const currentUser = frappeObj.session?.user;
		const info = currentUser
			? frappeObj.boot?.user_info?.[currentUser] || frappeObj.boot?.user
			: null;

		return info?.fullname || info?.full_name || "";
	};

	const mapGenderToSalutation = (gender) => {
		const g = (gender || "").toString().trim().toLowerCase();

		if (["male", "nam", "m", "anh"].includes(g)) return "anh";
		if (["female", "nu", "nữ", "f", "chi", "chị"].includes(g)) return "chị";
		return DEFAULT_SALUTATION;
	};

	const normalizeDepartmentName = (department) => {
		const raw = (department || "").toString().trim();
		if (!raw) return "";

		// Remove trailing company suffix, e.g. "Ban CNTT ... - VGT" -> "Ban CNTT ..."
		return raw.replace(/\s-\s[^-]+$/, "").trim();
	};

	const getCurrentUserProfile = () => {
		if (userProfilePromise) return userProfilePromise;

		const frappeObj = window?.frappe;
		if (!frappeObj) {
			return Promise.resolve({
				gender: DEFAULT_SALUTATION,
				designation: "",
				department: "",
			});
		}

		const currentUser = frappeObj.session?.user;
		const info =
			currentUser && (frappeObj.boot?.user_info?.[currentUser] || frappeObj.boot?.user);

		userProfilePromise = new Promise((resolve) => {
			frappeObj.call({
				method: "vinatex.api.user.get_current_user_gender",
				callback: (r) => resolve(r?.message || {}),
				error: () => resolve({}),
			});
		})
			.then((profile) => ({
				gender: mapGenderToSalutation(profile?.gender || info?.gender),
				designation: (profile?.designation || "").toString().trim(),
				department: normalizeDepartmentName(profile?.department),
			}))
			.catch(() => ({
				gender: mapGenderToSalutation(info?.gender),
				designation: "",
				department: "",
			}));

		return userProfilePromise;
	};

	const TITLE = "NHÀ MÁY SỢI VINATEX NAM ĐỊNH";
	const getSubtitleText = async () => {
		const name = getUserFullName();
		if (!name) return "";
		const profile = await getCurrentUserProfile();
		const extraInfo = [profile.designation, profile.department]
			.filter(Boolean)
			.join(" - ");
		return extraInfo
			? `Xin chào ${profile.gender} ${name} (${extraInfo})`
			: `Xin chào ${profile.gender} ${name}`;
	};
	const HOME_SIDE_LINES = [
		"",
		"",
	];

	const removeOldBrandText = () => {
		document.querySelectorAll(".vnt-brand-text").forEach((el) => el.remove());
	};

	const hideBreadcrumbs = () => {
		const selectors = [
			"#navbar-breadcrumbs",
			".navbar-breadcrumbs",
			".navbar-breadcrumbs-container",
			".breadcrumb-container",
		];
		selectors.forEach((sel) => {
			document.querySelectorAll(sel).forEach((el) => {
				el.style.display = "none";
			});
		});
	};

	const stripDefaultBrandText = () => {
		const brand =
			document.querySelector("header.navbar .navbar-brand") ||
			document.querySelector(".navbar .navbar-brand");
		if (!brand) return;

		const imgs = Array.from(brand.querySelectorAll("img"));
		// clear everything
		brand.textContent = "";
		brand.innerHTML = "";
		imgs.forEach((img) => brand.appendChild(img));
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
				<div class="vnt-search-subtitle"></div>
			`;
			navbar.appendChild(title);
		} else if (title.parentElement !== navbar) {
			navbar.appendChild(title);
		}

		const subtitleEl = title.querySelector(".vnt-search-subtitle");
		if (subtitleEl) {
			const renderSubtitle = (text) => {
				if (text) {
					subtitleEl.textContent = text;
					subtitleEl.style.fontStyle = "italic";
					subtitleEl.style.display = "";
				} else {
					subtitleEl.textContent = "";
					subtitleEl.style.display = "none";
				}
			};

			// Clear first, then populate when gender/name resolve
			renderSubtitle("");
			getSubtitleText()
				.then((text) => renderSubtitle(text))
				.catch(() => renderSubtitle(""));
		}
	};

	const removeHomeSideLines = () => {
		document
			.querySelectorAll(".vnt-home-inline-text")
			.forEach((el) => el.remove());
		document
			.querySelectorAll(".page-head.vnt-home-inline-text-active")
			.forEach((el) => el.classList.remove("vnt-home-inline-text-active"));
	};

	const ensureHomeSideLines = () => {
		const route = (window.frappe?.get_route && window.frappe.get_route()) || [];
		const primary = (route[0] || "").toLowerCase();
		const secondary = (route[1] || "").toLowerCase();
		const isWorkspaceHome =
			primary === "workspaces" &&
			(secondary === "" || secondary === "home");
		const isHomeRoute = primary === "home" || primary === "";
		const isHome = isWorkspaceHome || isHomeRoute;

		const pageHead = document.querySelector(".page-head");
		const container =
			pageHead?.querySelector(".page-head-content") || pageHead;

		if (!pageHead || !container || !isHome) {
			removeHomeSideLines();
			return;
		}

		let wrapper = container.querySelector(".vnt-home-inline-text");
		if (!wrapper) {
			wrapper = document.createElement("div");
			wrapper.className = "vnt-home-inline-text";
			container.appendChild(wrapper);
		}

		wrapper.innerHTML = "";
		HOME_SIDE_LINES.filter(Boolean).forEach((line, idx) => {
			const lineEl = document.createElement("div");
			lineEl.className = `vnt-home-inline-text-line ${
				idx === 0 ? "primary" : "secondary"
			}`;
			lineEl.textContent = line;
			wrapper.appendChild(lineEl);
		});

		if (!wrapper.childElementCount) {
			wrapper.remove();
			return;
		}

		pageHead.classList.add("vnt-home-inline-text-active");
	};

	const init = () => {
		stripDefaultBrandText();
		removeOldBrandText();
		hideBreadcrumbs();
		ensureHomeSideLines();
		setTimeout(() => {
			stripDefaultBrandText();
			removeOldBrandText();
			hideBreadcrumbs();
			ensureSearchTitle();
			ensureHomeSideLines();
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
