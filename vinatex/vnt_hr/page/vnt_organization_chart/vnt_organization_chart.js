frappe.pages["vnt-organization-chart"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sơ đồ tổ chức"),
		single_column: true,
	});

	const chart = new VNTOrganizationChart(page);
	wrapper.vnt_organization_chart = chart;
	chart.init();
};

frappe.pages["vnt-organization-chart"].on_page_show = function (wrapper) {
	const chart = wrapper.vnt_organization_chart;
	if (chart && chart.loaded) chart.refresh();
};

class VNTOrganizationChart {
	constructor(page) {
		this.page = page;
		this.$main = $(page.main);
		this.nodes = [];
		this.nodeMap = new Map();
		this.roots = [];
		this.expanded = new Set();
		this.zoom = 1;
		this.loaded = false;
		this.firstLoad = true;
		this.searchQuery = "";
		this.heading = "";
	}

	init() {
		this.setupPageActions();
		this.renderShell();
		this.bindEvents();
		this.refresh();
	}

	setupPageActions() {
		this.page.clear_inner_toolbar();
		if (frappe.model.can_write("VNT Organizational Structure")) {
			this.page.add_inner_button(__("Chỉnh sửa dữ liệu"), () => {
				frappe.set_route("Tree", "VNT Organizational Structure");
			});
		}
		this.page.add_inner_button(__("Làm mới"), () => this.refresh());
	}

	renderShell() {
		this.$main.addClass("vnt-org-page-main");
		this.$main.html(`
			<div class="vnt-org-page">
				<section class="vnt-org-panel">
					<div class="vnt-org-toolbar">
						<div class="vnt-org-search-wrap">
							<span class="vnt-org-search-icon">${frappe.utils.icon("search", "sm")}</span>
							<input class="form-control vnt-org-search" type="search" placeholder="${__("Tìm đơn vị trong sơ đồ")}">
						</div>
						<div class="vnt-org-actions">
							<span class="vnt-org-total"><strong data-role="total">0</strong> ${__("đơn vị")}</span>
							<button class="btn btn-sm btn-default" data-action="expand-all">${__("Mở tất cả")}</button>
							<button class="btn btn-sm btn-default" data-action="collapse-all">${__("Thu gọn")}</button>
							<button class="btn btn-sm btn-default" data-action="zoom-out">${__("Thu nhỏ")}</button>
							<button class="btn btn-sm btn-default vnt-org-zoom-value" data-role="zoom">100%</button>
							<button class="btn btn-sm btn-default" data-action="zoom-in">${__("Phóng to")}</button>
						</div>
					</div>

					<div class="vnt-org-status" data-role="status">${__("Đang tải dữ liệu...")}</div>
					<div class="vnt-org-viewport">
						<div class="vnt-org-loading" data-role="loading">${__("Đang tải sơ đồ tổ chức...")}</div>
						<div class="vnt-org-canvas" data-role="canvas"></div>
					</div>

					<footer class="vnt-org-footer">
						<div class="vnt-org-legend">
							<span><i class="is-leadership"></i>${__("Ban lãnh đạo")}</span>
							<span><i class="is-maintenance"></i>${__("Bảo toàn / Bảo trì")}</span>
							<span><i class="is-production"></i>${__("Sản xuất trực tiếp")}</span>
						</div>
						<div>${__("Chọn tên đơn vị để mở chi tiết; sơ đồ phản ánh dữ liệu hiện có trong danh mục.")}</div>
					</footer>
				</section>
			</div>
		`);
	}

	bindEvents() {
		this.$main.on("click.vnt-org", "[data-action]", (event) => {
			const $button = $(event.currentTarget);
			const action = $button.data("action");
			if (action === "expand-all") this.expandAll();
			if (action === "collapse-all") this.collapseAll();
			if (action === "zoom-out") this.setZoom(this.zoom - 0.1);
			if (action === "zoom-in") this.setZoom(this.zoom + 0.1);
		});

		this.$main.on("click.vnt-org", ".vnt-org-node-toggle", (event) => {
			event.stopPropagation();
			const id = $(event.currentTarget).closest(".vnt-org-node-card").data("node-id");
			this.toggleNode(String(id));
		});

		this.$main.on("click.vnt-org", ".vnt-org-node-name", (event) => {
			event.preventDefault();
			const id = $(event.currentTarget).closest(".vnt-org-node-card").data("node-id");
			frappe.set_route("Form", "VNT Organizational Structure", String(id));
		});

		let searchTimer;
		this.$main.on("input.vnt-org", ".vnt-org-search", (event) => {
			clearTimeout(searchTimer);
			searchTimer = setTimeout(() => this.applySearch(event.target.value), 180);
		});
	}

	refresh() {
		this.$main.find('[data-role="loading"]').show().text(__("Đang tải sơ đồ tổ chức..."));
		this.$main.find('[data-role="canvas"]').empty();

		return frappe
			.call({
				method: "vinatex.vnt_hr.page.vnt_organization_chart.vnt_organization_chart.get_chart_data",
			})
			.then((response) => {
				const data = response.message || {};
				this.prepareData(data.nodes || []);
				this.heading = data.heading || "";
				this.$main.find('[data-role="total"]').text(data.total || 0);
				this.$main
					.find('[data-role="status"]')
					.text(data.message || __("Sơ đồ đã được cập nhật từ dữ liệu hiện tại"));
				this.$main.find('[data-role="loading"]').hide();
				this.renderTree();
				this.loaded = true;
			})
			.catch(() => {
				this.$main
					.find('[data-role="loading"]')
					.show()
					.text(__("Không thể tải dữ liệu sơ đồ tổ chức."));
			});
	}

	prepareData(nodes) {
		this.nodes = nodes.map((node) => ({ ...node, children: [], depth: 0 }));
		this.nodeMap = new Map(this.nodes.map((node) => [String(node.id), node]));
		this.roots = [];

		this.nodes.forEach((node) => {
			const parent = this.nodeMap.get(String(node.parent || ""));
			if (parent && parent.id !== node.id) {
				node.parentNode = parent;
				parent.children.push(node);
			} else {
				this.roots.push(node);
			}
		});

		const setDepth = (node, depth, visited = new Set()) => {
			if (visited.has(node.id)) return;
			visited.add(node.id);
			node.depth = depth;
			node.children.forEach((child) => setDepth(child, depth + 1, new Set(visited)));
		};
		this.roots.forEach((root) => setDepth(root, 0));

		if (this.firstLoad) {
			this.expanded.clear();
			this.nodes.filter((node) => {
				if (!node.children.length || node.depth === 0) return node.depth === 0;
				const normalizedName = this.normalize(node.name);
				const hasGroupChild = node.children.some((child) => child.is_group || child.children.length);
				return normalizedName.includes("ban-giam-doc") || hasGroupChild || node.depth > 1;
			}).forEach((node) => {
				this.expanded.add(String(node.id));
			});
			this.firstLoad = false;
		}
	}

	renderTree() {
		const $canvas = this.$main.find('[data-role="canvas"]');
		if (!this.roots.length) {
			$canvas.html(`<div class="vnt-org-empty">${__("Chưa có dữ liệu Cơ cấu tổ chức.")}</div>`);
			return;
		}

		const layout = this.getReferenceLayout();
		if (layout) {
			$canvas.html(this.renderReferenceLayout(layout));
		} else {
			const tree = `<ul class="vnt-org-tree">${this.roots
				.map((root) => this.renderBranch(root))
				.join("")}</ul>`;
			$canvas.html(tree);
		}
		this.setZoom(this.zoom);
		this.markSearchMatches();
	}

	getReferenceLayout() {
		if (this.roots.length !== 1) return null;
		const root = this.roots[0];
		const leadership = root.children.find((node) => {
			const name = this.normalize(node.name);
			return name.includes("ban-giam-doc") || node.children.some((child) => this.normalize(child.name).includes("giam-doc"));
		});
		if (!leadership) return null;

		const departments = root.children.filter((node) => node !== leadership);
		const operatingDepartment = departments.find((node) =>
			node.children.some((child) => child.is_group || child.children.length)
		);
		if (!departments.length || !operatingDepartment) return null;

		const directors = leadership.children.filter((node) => !this.normalize(node.name).includes("pho-giam-doc"));
		const deputies = leadership.children.filter((node) => this.normalize(node.name).includes("pho-giam-doc"));
		const divisions = operatingDepartment.children.filter((node) => node.is_group || node.children.length);

		return {
			root,
			leadership,
			director: directors[0] || leadership,
			deputies,
			departments,
			operatingDepartment,
			divisions,
		};
	}

	renderReferenceLayout(layout) {
		const companyName = this.escape(this.heading || layout.root.name);
		const deputies = layout.deputies.length
			? layout.deputies.map((node) => this.renderLeadershipCard(node, "is-deputy")).join("")
			: "";
		const departments = layout.departments.map((node) =>
			this.renderDepartment(node, node === layout.operatingDepartment)
		).join("");
		const divisions = layout.divisions.map((node, index) => this.renderDivision(node, index)).join("");

		return `
			<div class="vnt-org-diagram">
				<header class="vnt-org-diagram-title">
					<h1>${__("SƠ ĐỒ TỔ CHỨC")}</h1>
					<p>${companyName}</p>
				</header>
				<section class="vnt-org-leadership" aria-label="${__("Ban lãnh đạo")}">
					<div class="vnt-org-director-wrap">${this.renderLeadershipCard(layout.director, "is-director")}</div>
					${deputies ? `<div class="vnt-org-deputies">${deputies}</div>` : ""}
				</section>
				<section class="vnt-org-departments" aria-label="${__("Các phòng ban")}">${departments}</section>
				${divisions ? `<section class="vnt-org-divisions" aria-label="${__("Các khối trực thuộc")}">${divisions}</section>` : ""}
			</div>`;
	}

	renderLeadershipCard(node, extraClass) {
		return `
			<div class="vnt-org-node-card vnt-org-leader-card ${extraClass}" data-node-id="${this.escape(node.id)}">
				<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
			</div>`;
	}

	renderDepartment(node, isOperating) {
		const id = String(node.id);

		return `
			<div class="vnt-org-department-cell ${isOperating ? "is-operating" : ""}">
				<div class="vnt-org-node-card vnt-org-department-card" data-node-id="${this.escape(id)}">
					<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
				</div>
			</div>`;
	}

	renderCompactBranch(node) {
		return `
			<div class="vnt-org-node-card vnt-org-support-card ${this.getNodeClass(node)}" data-node-id="${this.escape(node.id)}">
				<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
			</div>`;
	}

	renderDivision(node, index) {
		const id = String(node.id);
		const isExpanded = this.expanded.has(id);
		const normalized = this.normalize(node.name);
		let tone = index % 2 ? "production" : "maintenance";
		if (normalized.includes("bao-toan") || normalized.includes("bao-tri")) tone = "maintenance";
		if (normalized.includes("san-xuat")) tone = "production";
		const supervisor = tone === "production"
			? node.children.find((child) => this.normalize(child.name).includes("truong-ca"))
			: null;
		const branchNodes = supervisor ? supervisor.children : node.children;
		const branches = isExpanded
			? `${supervisor ? this.renderDivisionSupervisor(supervisor, tone) : ""}
				<div class="vnt-org-division-branches ${supervisor ? "has-supervisor" : ""}">${branchNodes
				.map((child) => this.renderDivisionBranch(child, tone))
				.join("")}</div>`
			: "";
		const branchCount = Math.max(branchNodes.length, 1);

		return `
			<div class="vnt-org-division is-${tone}" style="--branch-count: ${branchCount}; --edge-offset: ${50 / branchCount}%">
				<div class="vnt-org-node-card vnt-org-division-title" data-node-id="${this.escape(id)}">
					<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
					${node.children.length ? `<button class="vnt-org-node-toggle" type="button">${isExpanded ? __("Thu gọn") : __("Mở rộng")}</button>` : ""}
				</div>
				${branches}
			</div>`;
	}

	renderDivisionSupervisor(node, tone) {
		return `
			<div class="vnt-org-division-supervisor is-${tone}">
				<div class="vnt-org-node-card vnt-org-supervisor-card is-${tone}" data-node-id="${this.escape(node.id)}">
					<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
				</div>
			</div>`;
	}

	renderDivisionBranch(node, tone) {
		return `
			<div class="vnt-org-branch-column">
				<div class="vnt-org-node-card vnt-org-process-card is-${tone}" data-node-id="${this.escape(node.id)}">
					<a class="vnt-org-node-name" href="#">${this.escape(this.getShortBranchName(node.name))}</a>
				</div>
				${this.renderRoleChain(node.children, tone)}
			</div>`;
	}

	renderRoleChain(nodes, tone) {
		if (!nodes || !nodes.length) return "";
		return `<div class="vnt-org-role-chain is-${tone}">${nodes.map((node) => `
			<div class="vnt-org-node-card vnt-org-role-card is-${tone}" data-node-id="${this.escape(node.id)}">
				<a class="vnt-org-node-name" href="#">${this.escape(this.getShortRoleName(node.name))}</a>
			</div>
			${this.renderRoleChain(node.children, tone)}`).join("")}</div>`;
	}

	getShortBranchName(value) {
		return String(value || "").replace(/\s+-\s+(Bảo toàn|Bảo trì|Sản xuất).*$/i, "");
	}

	getShortRoleName(value) {
		return String(value || "").replace(
			/^(Trưởng CĐ|Phó trưởng CĐ|CN bảo toàn|Tổ trưởng SX|Tổ phó SX|CN công nghệ)\s+-.*$/i,
			"$1"
		);
	}

	renderBranch(node) {
		const id = String(node.id);
		const hasChildren = node.children.length > 0;
		const isExpanded = this.expanded.has(id);
		const nodeClass = this.getNodeClass(node);
		const childLabel = node.children.length === 1 ? __("đơn vị cấp dưới") : __("đơn vị cấp dưới");
		const children = hasChildren && isExpanded
			? `<ul>${node.children.map((child) => this.renderBranch(child)).join("")}</ul>`
			: "";

		return `
			<li>
				<div class="vnt-org-node-card ${nodeClass}" data-node-id="${this.escape(id)}">
					<div class="vnt-org-node-type">${this.getNodeTypeLabel(node)}</div>
					<a class="vnt-org-node-name" href="#">${this.escape(node.name)}</a>
					<div class="vnt-org-node-count">${node.children.length} ${childLabel}</div>
					${
						hasChildren
							? `<button class="vnt-org-node-toggle" type="button">${
									isExpanded ? __("Thu gọn") : __("Mở rộng")
							  }</button>`
							: ""
					}
				</div>
				${children}
			</li>`;
	}

	getNodeClass(node) {
		if (node.depth === 0) return "is-root";
		const level = this.normalize(node.level);
		return level.includes("truc-thuoc") ? "is-subordinate" : "is-managed";
	}

	getNodeTypeLabel(node) {
		return this.getNodeClass(node) === "is-subordinate" ? __("TRỰC THUỘC") : __("QUẢN LÝ");
	}

	toggleNode(id) {
		if (this.expanded.has(id)) this.expanded.delete(id);
		else this.expanded.add(id);
		this.renderTree();
	}

	expandAll() {
		this.nodes.filter((node) => node.children.length).forEach((node) => this.expanded.add(String(node.id)));
		this.renderTree();
	}

	collapseAll() {
		this.expanded.clear();
		this.roots.filter((node) => node.children.length).forEach((node) => this.expanded.add(String(node.id)));
		this.renderTree();
	}

	setZoom(value) {
		this.zoom = Math.min(1.4, Math.max(0.4, Math.round(value * 10) / 10));
		this.$main.find('[data-role="canvas"]').css("zoom", this.zoom);
		this.$main.find('[data-role="zoom"]').text(`${Math.round(this.zoom * 100)}%`);
	}

	applySearch(value) {
		this.searchQuery = this.normalize(value);
		if (this.searchQuery) {
			this.nodes.forEach((node) => {
				if (!this.normalize(node.name).includes(this.searchQuery)) return;
				let parent = node.parentNode;
				while (parent) {
					this.expanded.add(String(parent.id));
					parent = parent.parentNode;
				}
			});
		}
		this.renderTree();

		if (this.searchQuery) {
			const $match = this.$main.find(".vnt-org-node-card.is-match").first();
			if ($match.length) $match[0].scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
		}
	}

	markSearchMatches() {
		if (!this.searchQuery) return;
		this.$main.find(".vnt-org-node-card").each((_index, element) => {
			const id = String($(element).data("node-id"));
			const node = this.nodeMap.get(id);
			if (node && this.normalize(node.name).includes(this.searchQuery)) $(element).addClass("is-match");
		});
	}

	normalize(value) {
		return (value || "")
			.toString()
			.normalize("NFD")
			.replace(/[\u0300-\u036f]/g, "")
			.replace(/đ/g, "d")
			.replace(/Đ/g, "D")
			.replace(/[^a-zA-Z0-9]+/g, "-")
			.replace(/^-+|-+$/g, "")
			.toLowerCase();
	}

	escape(value) {
		return $("<div>").text(value == null ? "" : String(value)).html();
	}
}
