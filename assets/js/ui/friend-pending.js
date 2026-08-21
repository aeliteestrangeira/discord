import { appUrl, emit } from "./runtime.js";
import { replaceTrustedChildren } from "./dom.js";

const DEFAULT_AVATAR = appUrl("images/0208-2ccd8ae8b2379360.png");
const SEARCH_ICON = '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><path fill="var(--icon-strong)" fill-rule="evenodd" d="M15.62 17.03a9 9 0 1 1 1.41-1.41l4.68 4.67a1 1 0 0 1-1.42 1.42l-4.67-4.68ZM17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z" clip-rule="evenodd"></path></svg>';
const ACCEPT_ICON = '<svg class="icon_f8fa06" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M21.7 5.3a1 1 0 0 1 0 1.4l-12 12a1 1 0 0 1-1.4 0l-6-6a1 1 0 1 1 1.4-1.4L9 16.58l11.3-11.3a1 1 0 0 1 1.4 0Z"></path></svg>';
const DENY_ICON = '<svg class="icon_f8fa06" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M17.3 18.7a1 1 0 0 0 1.4-1.4L13.42 12l5.3-5.3a1 1 0 0 0-1.42-1.4L12 10.58l-5.3-5.3a1 1 0 0 0-1.4 1.42L10.58 12l-5.3 5.3a1 1 0 1 0 1.42 1.4L12 13.42l5.3 5.3Z"></path></svg>';

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function tooltipPortal() {
  return document.querySelector("#popover-portal") || document.body;
}

function fixedContainingBlockOrigin(node) {
  let current = node?.parentElement || null;
  while (current && current !== document.documentElement) {
    const style = getComputedStyle(current);
    const establishesFixedBlock = style.transform !== "none" || style.perspective !== "none" || style.filter !== "none" || style.backdropFilter !== "none" || /transform|filter|perspective/.test(style.willChange || "");
    if (establishesFixedBlock) {
      const rect = current.getBoundingClientRect();
      return { left: rect.left, top: rect.top };
    }
    current = current.parentElement;
  }
  return { left: 0, top: 0 };
}

// One shared tooltip actor for every pending-row action. Accept/Ignore/Cancel do
// not own independent popovers, so rapid pointer movement can never leave two
// Discord tooltips mounted at the same time.
const ActionTooltip = (() => {
  let anchor = null;
  let tooltip = null;
  let resizeObserver = null;

  const position = () => {
    if (!anchor?.isConnected || !tooltip?.isConnected) return;
    const rect = anchor.getBoundingClientRect();
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    const gap = 8;
    const margin = 8;
    let left = rect.left + (rect.width - width) / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
    let top = rect.bottom + gap;
    let placement = "bottom";
    if (top + height > window.innerHeight - margin && rect.top - height - gap >= margin) {
      top = rect.top - height - gap;
      placement = "top";
    }
    tooltip.classList.toggle("tooltipBottom_c36707", placement === "bottom");
    tooltip.classList.toggle("tooltipTop_c36707", placement === "top");
    const origin = fixedContainingBlockOrigin(tooltip);
    tooltip.style.position = "fixed";
    tooltip.style.left = `${Math.round(left - origin.left)}px`;
    tooltip.style.top = `${Math.round(top - origin.top)}px`;
    const pointer = tooltip.querySelector(".tooltipPointer_c36707");
    if (pointer) pointer.style.insetInlineStart = `${Math.round(rect.left + rect.width / 2 - left)}px`;
  };

  const stopTracking = () => {
    resizeObserver?.disconnect();
    resizeObserver = null;
    window.removeEventListener("resize", position);
    window.removeEventListener("scroll", position, true);
  };

  const hide = (expectedAnchor = null) => {
    // A late mouseleave/blur from the previous button must not close a tooltip
    // that has already been reassigned to another action button.
    if (expectedAnchor && anchor !== expectedAnchor) return;
    stopTracking();
    tooltip?.remove();
    tooltip = null;
    anchor = null;
  };

  const show = (nextAnchor, label) => {
    if (!nextAnchor?.isConnected) return;
    if (anchor !== nextAnchor) hide();
    anchor = nextAnchor;
    if (!tooltip) {
      tooltip = make("div", "tooltip_c36707 tooltipPrimary_c36707 tooltipBottom_c36707");
      tooltip.dataset.appActionTooltip = "true";
      tooltip.setAttribute("role", "tooltip");
      tooltip.append(make("div", "tooltipContent_c36707"), make("div", "tooltipPointer_c36707"));
    }
    tooltip.querySelector(".tooltipContent_c36707").textContent = label;
    const portal = tooltipPortal();
    // Defensive cleanup for a hot-reload/old-version orphan. The current
    // controller still owns exactly one node after this operation.
    for (const stale of portal.querySelectorAll('[data-app-action-tooltip="true"]')) {
      if (stale !== tooltip) stale.remove();
    }
    if (!tooltip.isConnected) portal.appendChild(tooltip);
    position();
    stopTracking();
    if (typeof ResizeObserver === "function") {
      resizeObserver = new ResizeObserver(position);
      resizeObserver.observe(tooltip);
      resizeObserver.observe(nextAnchor);
    }
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
  };

  return Object.freeze({ show, hide, current: () => anchor });
})();

function wireActionTooltip(button, label) {
  button.addEventListener("mouseenter", () => ActionTooltip.show(button, label));
  button.addEventListener("mouseleave", () => ActionTooltip.hide(button));
  button.addEventListener("focus", () => ActionTooltip.show(button, label));
  button.addEventListener("blur", () => ActionTooltip.hide(button));
  button.addEventListener("click", () => ActionTooltip.hide(button));
  return () => ActionTooltip.hide(button);
}

function readPendingBootstrap() {
  const node = document.querySelector("#app-friend-pending-bootstrap");
  if (!node) return null;
  try {
    const parsed = JSON.parse(node.textContent || "{}");
    if (parsed.ready === false) return null;
    return {
      sent: Array.isArray(parsed.sent) ? parsed.sent : [],
      received: Array.isArray(parsed.received) ? parsed.received : [],
    };
  } catch (_) {
    return null;
  } finally {
    node.remove();
  }
}

function numberBadge(count, { tab = false, marker = "" } = {}) {
  const classes = ["eyebrow_cf4812"];
  if (tab) classes.push("badge__133bf");
  classes.push("numberBadge__463b7", "base__463b7", "baseShapeRound__463b7");
  const badge = make("div", classes.join(" "), String(count));
  badge.dataset.textVariant = "eyebrow";
  if (marker) badge.dataset[marker] = "true";
  badge.style.backgroundColor = "var(--badge-notification-background)";
  badge.style.width = count > 9 ? "auto" : "16px";
  if (count > 9) badge.style.padding = "0 4px";
  if (tab) {
    // Preserve Discord's original badge classes while fixing the tab-specific
    // glyph alignment explicitly. The sidebar badge already renders correctly.
    badge.style.height = "16px";
    badge.style.minWidth = "16px";
    badge.style.boxSizing = "border-box";
    badge.style.display = "flex";
    badge.style.alignItems = "center";
    badge.style.justifyContent = "center";
    badge.style.lineHeight = "16px";
  }
  return badge;
}

function syncFriendsSidebarBadge(incomingCount) {
  const link = document.querySelector('.friendsButtonContainer_e6b769 a.link__972a0[data-list-item-id$="___friends"]');
  if (!link) return;
  link.querySelector('[data-app-friend-incoming-badge="true"]')?.remove();
  if (incomingCount <= 0) return;
  link.appendChild(numberBadge(incomingCount, { marker: "appFriendIncomingBadge" }));
}

function buildPendingTab(incomingCount) {
  const tab = make("div", "item__133bf item_aa8da2 themed_aa8da2");
  tab.dataset.appPendingTab = "true";
  tab.setAttribute("role", "tab");
  tab.setAttribute("aria-selected", "false");
  tab.setAttribute("aria-disabled", "false");
  tab.setAttribute("tabindex", "-1");
  tab.setAttribute("aria-controls", "pending-tab");
  const text = make("div", "text-md/medium_cf4812 itemText_aa8da2");
  text.dataset.textVariant = "text-md/medium";
  tab.appendChild(text);
  syncPendingTab(tab, incomingCount);
  return tab;
}

function syncPendingTab(tab, incomingCount) {
  const text = tab.querySelector(".itemText_aa8da2");
  if (!text) return;
  text.replaceChildren(document.createTextNode("Pendentes"));
  if (incomingCount > 0) text.appendChild(numberBadge(incomingCount, { tab: true }));
  tab.setAttribute("aria-label", incomingCount > 0 ? `Pendentes, ${incomingCount} novo${incomingCount === 1 ? "" : "s"}` : "Pendentes");
}

function buildAvatar(item, globalName) {
  const avatar = make("div", "wrapper__44b0c avatar__0a06e");
  avatar.setAttribute("role", "img");
  avatar.setAttribute("aria-label", globalName);
  avatar.setAttribute("aria-hidden", "false");
  avatar.style.width = "32px";
  avatar.style.height = "32px";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "32");
  svg.setAttribute("height", "32");
  svg.setAttribute("viewBox", "0 0 32 32");
  svg.setAttribute("class", "mask__44b0c svg__44b0c");
  svg.setAttribute("aria-hidden", "true");
  const fo = document.createElementNS("http://www.w3.org/2000/svg", "foreignObject");
  fo.setAttribute("x", "0");
  fo.setAttribute("y", "0");
  fo.setAttribute("width", "32");
  fo.setAttribute("height", "32");
  fo.setAttribute("mask", "url(#svg-mask-avatar-default)");
  const stack = make("div", "avatarStack__44b0c");
  const img = make("img", "avatar__44b0c");
  img.alt = " ";
  img.setAttribute("aria-hidden", "true");
  img.src = item.avatar_url || DEFAULT_AVATAR;
  img.addEventListener("error", () => {
    if (img.src !== new URL(DEFAULT_AVATAR, location.href).href) img.src = DEFAULT_AVATAR;
  }, { once: true });
  stack.appendChild(img);
  fo.appendChild(stack);
  svg.appendChild(fo);
  avatar.appendChild(svg);
  return avatar;
}

function makeActionButton({ className, label, hiddenId, icon, invoke }) {
  const action = make("div", `actionButton_f8fa06 ${className}`);
  action.setAttribute("aria-label", label);
  action.setAttribute("tabindex", "-1");
  action.setAttribute("aria-describedby", hiddenId);
  action.setAttribute("role", "button");
  replaceTrustedChildren(action, icon);
  let busy = false;
  const run = async () => {
    if (busy) return;
    busy = true;
    action.setAttribute("aria-disabled", "true");
    try { await invoke(); }
    finally {
      busy = false;
      if (action.isConnected) action.removeAttribute("aria-disabled");
    }
  };
  action.addEventListener("click", run);
  wireActionTooltip(action, label);
  return action;
}

function buildPendingRow(item, direction, handlers) {
  const globalName = String(item.global_name || item.username || "Usuário").trim();
  const username = String(item.username || "").trim().toLowerCase();
  const requestId = String(item.request_id || "");
  const peerId = String(item.peer_id || item.receiver_id || item.sender_id || "");
  const incoming = direction === "received";

  const row = make("div", "peopleListItem_cc6179 text-md/medium_cc6179");
  row.setAttribute("role", "listitem");
  row.style.height = "61px";
  row.style.opacity = "1";
  row.dataset.requestId = requestId;
  row.dataset.direction = direction;
  row.dataset.searchText = `${globalName} ${username}`.toLocaleLowerCase("pt-BR");

  const rowButton = make("div", "rowButton_cc6179");
  rowButton.setAttribute("aria-label", incoming ? `Ver pedido de amizade pendente de ${globalName}` : `Ver pedido de amizade pendente para ${globalName}`);
  rowButton.dataset.listItemId = `people___${peerId}`;
  rowButton.setAttribute("tabindex", "-1");
  rowButton.setAttribute("role", "button");

  const rowContent = make("div", "rowContent_cc6179");
  const contents = make("div", "listItemContents_e1ecd3");
  const userInfo = make("div", "userInfo__0a06e");
  userInfo.appendChild(buildAvatar(item, globalName));

  const text = make("div", "text__0a06e");
  const info = make("div", "info_f4bc97 discordTag__0a06e alignUniqueUsername__0a06e");
  info.appendChild(make("span", "username__0a06e", globalName));
  const subtext = make("div", "subtext__0a06e");
  const appLabel = make("div", "applicationSublabel_e1ecd3");
  const usernameNode = make("div", "text-sm/medium_cf4812", username);
  usernameNode.dataset.textVariant = "text-sm/medium";
  usernameNode.style.color = "var(--text-subtle)";
  appLabel.appendChild(usernameNode);
  subtext.appendChild(appLabel);
  text.append(info, subtext);
  userInfo.appendChild(text);

  const actions = make("div", "actions_e1ecd3");
  if (incoming) {
    const acceptId = `app-accept-${requestId}`;
    const ignoreId = `app-ignore-${requestId}`;
    actions.append(
      makeActionButton({ className: "actionAccept_f8fa06", label: "Aceitar", hiddenId: acceptId, icon: ACCEPT_ICON, invoke: () => handlers.accept(item) }),
      Object.assign(make("span", "hiddenVisually_b18fe2", "Aceitar"), { id: acceptId }),
      makeActionButton({ className: "actionDeny_f8fa06", label: "Ignorar", hiddenId: ignoreId, icon: DENY_ICON, invoke: () => handlers.ignore(item) }),
      Object.assign(make("span", "hiddenVisually_b18fe2", "Ignorar"), { id: ignoreId }),
    );
  } else {
    const cancelId = `app-cancel-${requestId}`;
    actions.append(
      makeActionButton({ className: "actionDeny_f8fa06", label: "Cancelar", hiddenId: cancelId, icon: DENY_ICON, invoke: () => handlers.cancel(item) }),
      Object.assign(make("span", "hiddenVisually_b18fe2", "Cancelar"), { id: cancelId }),
    );
  }

  contents.append(userInfo, actions);
  rowContent.appendChild(contents);
  row.append(rowButton, rowContent);
  return row;
}

function buildSection(label, items, direction, handlers) {
  const section = make("div");
  section.dataset.appPendingSection = direction;
  const titleWrap = make("div", "sectionTitle__5ec2f");
  const title = make("h2", "text-sm/medium_cf4812 defaultColor__5345c title__1472a container__13cf1", `${label} — ${items.length}`);
  title.dataset.textVariant = "text-sm/medium";
  title.dataset.appPendingSectionTitle = direction;
  titleWrap.appendChild(title);
  section.appendChild(titleWrap);
  items.forEach((item) => {
    section.append(make("div", "divider_cc6179"), buildPendingRow(item, direction, handlers));
  });
  return section;
}

function buildPendingPanel(state, handlers) {
  const panel = make("div", "peopleColumn__133bf");
  panel.dataset.appPendingPanel = "true";
  panel.setAttribute("aria-labelledby", "app-pending-title");
  panel.setAttribute("role", "tabpanel");
  panel.id = "pending-tab";
  panel.setAttribute("tabindex", "-1");

  const searchBar = make("div", "searchBar__5ec2f");
  const container = make("div", "container__5a838");
  container.dataset.layout = "vertical";
  const control = make("div", "control__5a838");
  const fieldContainer = make("div", "container__72c38");
  fieldContainer.dataset.fullWidth = "true";
  const wrapper = make("div", "wrapper__72c38 container__75098 md__75098 text-md/normal_cf4812 hasLeading__75098");
  wrapper.dataset.error = "false";
  wrapper.dataset.disabled = "false";
  const icon = make("div", "icon__75098");
  replaceTrustedChildren(icon, SEARCH_ICON);
  const input = make("input", "input__75098");
  input.placeholder = "Pesquisar";
  input.setAttribute("data-mana-component", "text-input");
  input.setAttribute("aria-label", "Pesquisar");
  input.id = "app-pending-search";
  input.setAttribute("aria-invalid", "false");
  input.type = "text";
  wrapper.append(icon, input);
  fieldContainer.appendChild(wrapper);
  control.appendChild(fieldContainer);
  container.appendChild(control);
  searchBar.appendChild(container);

  const live = make("span", "hiddenVisually_b18fe2");
  live.setAttribute("aria-live", "polite");
  live.setAttribute("role", "status");

  const list = make("div", "peopleList__5ec2f scrollbarGutterStable_d125d2 auto_d125d2 scrollerBase_d125d2");
  list.setAttribute("dir", "ltr");
  list.setAttribute("role", "list");
  list.setAttribute("tabindex", "0");
  list.dataset.listId = "people";
  list.setAttribute("aria-orientation", "vertical");
  list.style.overflow = "hidden scroll";
  const inner = make("div");
  const firstTitle = document.createElement("span");
  firstTitle.id = "app-pending-title";
  firstTitle.className = "hiddenVisually_b18fe2";
  firstTitle.textContent = "Pedidos de amizade pendentes";
  inner.appendChild(firstTitle);
  if (state.received.length > 0) inner.appendChild(buildSection("Recebidos", state.received, "received", handlers));
  if (state.sent.length > 0) inner.appendChild(buildSection("Enviados", state.sent, "sent", handlers));
  list.appendChild(inner);
  panel.append(searchBar, live, list);

  input.addEventListener("input", () => {
    const needle = input.value.trim().toLocaleLowerCase("pt-BR");
    let shown = 0;
    for (const section of inner.querySelectorAll("[data-app-pending-section]")) {
      let sectionShown = 0;
      for (const row of section.querySelectorAll(".peopleListItem_cc6179")) {
        const visible = !needle || row.dataset.searchText.includes(needle);
        row.hidden = !visible;
        const divider = row.previousElementSibling;
        if (divider?.classList.contains("divider_cc6179")) divider.hidden = !visible;
        if (visible) {
          sectionShown += 1;
          shown += 1;
        }
      }
      section.hidden = sectionShown === 0;
    }
    live.textContent = `${shown} pedido${shown === 1 ? "" : "s"} exibido${shown === 1 ? "" : "s"}.`;
  });
  return panel;
}

function setSelected(tab, selected) {
  tab.classList.toggle("selected_aa8da2", selected);
  tab.setAttribute("aria-selected", selected ? "true" : "false");
  tab.setAttribute("tabindex", selected ? "0" : "-1");
}

let activePendingController = null;

export function wirePendingFriendRequests(authProvider) {
  const main = document.querySelector("main.container__133bf");
  const tabBar = main?.querySelector(".tabBar__133bf");
  const addTab = tabBar?.querySelector(".addFriend__133bf");
  const tabBody = main?.querySelector(".tabBody__133bf");
  const addPanel = tabBody?.querySelector("#add_friend-tab.peopleColumn__133bf");
  const nowPlaying = tabBody?.querySelector(".nowPlayingColumn__133bf");
  if (!main || !tabBar || !addTab || !tabBody || !addPanel) {
    activePendingController?.stop?.();
    return null;
  }
  if (activePendingController?.main === main) return activePendingController;
  activePendingController?.stop?.();

  const bootstrap = readPendingBootstrap();
  const state = {
    sent: bootstrap?.sent || [],
    received: bootstrap?.received || [],
  };
  let pendingTab = tabBar.querySelector('[data-app-pending-tab="true"]');
  let pendingPanel = null;
  let active = "add";
  let refreshBusy = false;

  const totalPending = () => state.sent.length + state.received.length;
  const incomingCount = () => state.received.length;

  const syncNavigation = () => {
    const total = totalPending();
    const incoming = incomingCount();
    syncFriendsSidebarBadge(incoming);
    if (total === 0) {
      pendingTab?.remove();
      pendingTab = null;
      return;
    }
    if (!pendingTab) {
      pendingTab = buildPendingTab(incoming);
      tabBar.insertBefore(pendingTab, addTab);
    } else {
      syncPendingTab(pendingTab, incoming);
    }
  };

  const showAdd = () => {
    ActionTooltip.hide();
    active = "add";
    if (pendingPanel?.isConnected) pendingPanel.replaceWith(addPanel);
    pendingPanel = null;
    if (pendingTab) setSelected(pendingTab, false);
    setSelected(addTab, true);
    addTab.setAttribute("aria-controls", "add_friend-tab");
    addPanel.focus({ preventScroll: true });
    emit("app:friends-view", { view: "add" });
  };

  const remountPending = () => {
    ActionTooltip.hide();
    const next = buildPendingPanel(state, handlers);
    if (pendingPanel?.isConnected) pendingPanel.replaceWith(next);
    else if (addPanel.isConnected) addPanel.replaceWith(next);
    else if (nowPlaying) tabBody.insertBefore(next, nowPlaying);
    else tabBody.appendChild(next);
    pendingPanel = next;
  };

  const afterMutation = () => {
    syncNavigation();
    if (totalPending() === 0) {
      showAdd();
      return;
    }
    if (active === "pending") remountPending();
  };

  const handlers = {
    cancel: async (item) => {
      const result = await authProvider.cancelFriendRequest(item.request_id);
      if (result.error) {
        emit("app:friend-request-cancel-error", { code: result.error.code || "friend_request_cancel_error" });
        return;
      }
      state.sent = state.sent.filter((entry) => entry.request_id !== item.request_id);
      afterMutation();
      emit("app:friend-request-cancelled", { requestId: item.request_id });
    },
    accept: async (item) => {
      const result = await authProvider.acceptFriendRequest(item.request_id);
      if (result.error) {
        emit("app:friend-request-accept-error", { code: result.error.code || "friend_request_accept_error" });
        return;
      }
      state.received = state.received.filter((entry) => entry.request_id !== item.request_id);
      afterMutation();
      emit("app:friend-request-accepted", { requestId: item.request_id });
    },
    ignore: async (item) => {
      const result = await authProvider.ignoreFriendRequest(item.request_id);
      if (result.error) {
        emit("app:friend-request-ignore-error", { code: result.error.code || "friend_request_ignore_error" });
        return;
      }
      state.received = state.received.filter((entry) => entry.request_id !== item.request_id);
      afterMutation();
      emit("app:friend-request-ignored", { requestId: item.request_id });
    },
  };

  const showPending = () => {
    if (!pendingTab || totalPending() === 0) return;
    active = "pending";
    remountPending();
    setSelected(addTab, false);
    setSelected(pendingTab, true);
    pendingPanel.focus({ preventScroll: true });
    emit("app:friends-view", { view: "pending", sent: state.sent.length, received: state.received.length });
  };

  const refresh = async ({ preserveView = true } = {}) => {
    if (refreshBusy) return;
    refreshBusy = true;
    try {
      const result = await authProvider.listPendingFriendRequests();
      if (result.error) {
        emit("app:friend-requests-list-error", { code: result.error.code || "friend_requests_list_error" });
        return;
      }
      const data = result.data || {};
      state.sent = Array.isArray(data.sent) ? data.sent : (Array.isArray(data.requests) ? data.requests : []);
      state.received = Array.isArray(data.received) ? data.received : [];
      syncNavigation();
      if (totalPending() === 0 && active === "pending") showAdd();
      else if (preserveView && active === "pending") remountPending();
    } finally {
      refreshBusy = false;
    }
  };

  addTab.addEventListener("click", showAdd);
  addTab.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    showAdd();
  });

  const wirePendingTab = () => {
    if (!pendingTab || pendingTab.dataset.appPendingWired === "true") return;
    pendingTab.dataset.appPendingWired = "true";
    pendingTab.addEventListener("click", showPending);
    pendingTab.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      showPending();
    });
  };

  const syncAndWire = async (options) => {
    await refresh(options);
    wirePendingTab();
  };

  const onFriendRequestSuccess = () => syncAndWire({ preserveView: true });
  const onFocus = () => syncAndWire({ preserveView: true });
  const onVisibility = () => {
    if (!document.hidden) syncAndWire({ preserveView: true });
  };
  document.addEventListener("app:friend-request-success", onFriendRequestSuccess);
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onVisibility);

  const controller = {
    main,
    stop() {
      document.removeEventListener("app:friend-request-success", onFriendRequestSuccess);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      ActionTooltip.hide();
      if (activePendingController === controller) activePendingController = null;
    },
  };
  activePendingController = controller;

  // The authenticated HTML response already contains the first pending snapshot
  // and notification chrome. Consume it synchronously instead of repainting the
  // page after a second request. Focus/visibility and mutation events refresh
  // state without a periodic network poll.
  if (bootstrap) {
    syncNavigation();
    wirePendingTab();
    emit("app:friend-requests-bootstrap-ready", { sent: state.sent.length, received: state.received.length });
  } else {
    syncAndWire({ preserveView: false });
  }
  return controller;
}
