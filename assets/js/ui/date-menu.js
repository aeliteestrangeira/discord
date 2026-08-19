import { State } from "./state.js";
import { dateOfBirthMenuCatalog } from "./menu-catalog.js";
import { OverlayManager } from "./overlay-manager.js";
import { SlidingHighlightController } from "./sliding-highlight.js";
import { replaceTrustedChildren } from "./dom.js";

function wireDateOfBirth() {
  if (State.page !== "register") return;

  const parts = {
    month: document.querySelector('[role="combobox"][aria-label="Mês"]'),
    day: document.querySelector('[role="combobox"][aria-label="Dia"]'),
    year: document.querySelector('[role="combobox"][aria-label="Ano"]')
  };
  if (!parts.month || !parts.day || !parts.year) return;

  const form = parts.month.closest("form") || document.querySelector("form");
  const checkmarkSvg = '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24"><path fill="currentColor" fill-rule="evenodd" d="M19.06 6.94a1.5 1.5 0 0 1 0 2.12l-8 8a1.5 1.5 0 0 1-2.12 0l-4-4a1.5 1.5 0 0 1 2.12-2.12L10 13.88l6.94-6.94a1.5 1.5 0 0 1 2.12 0Z" clip-rule="evenodd"></path></svg>';

  const fieldset = parts.month.closest("fieldset.container_b0f4cc.birthdayInput_d332d2");
  const fieldsetContainer = fieldset?.firstElementChild;
  const fieldsetControl = fieldsetContainer?.querySelector(":scope > .control__5a838");
  const dobErrorId = "app-register-dob-required";
  const dobErrorSvg = '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent" class=""></circle><path fill="var(--text-feedback-critical)" fill-rule="evenodd" d="M12 23a11 11 0 1 0 0-22 11 11 0 0 0 0 22Zm1.44-15.94L13.06 14a1.06 1.06 0 0 1-2.12 0l-.38-6.94a1 1 0 0 1 1-1.06h.88a1 1 0 0 1 1 1.06Zm-.19 10.69a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" clip-rule="evenodd" class=""></path></svg>';
  let dobSubmitAttempted = false;

  function clearDobError() {
    fieldsetControl?.querySelector('[data-app-dob-error="true"]')?.remove();
    for (const combo of Object.values(parts)) combo.setAttribute("aria-invalid", "false");
  }

  function showDobError(message = "Obrigatório") {
    if (!fieldsetControl) return;
    const existing = fieldsetControl.querySelector('[data-app-dob-error="true"]');
    if (existing) {
      const existingText = existing.querySelector(`#${dobErrorId}`);
      if (existingText && existingText.textContent !== message) existingText.textContent = message;
      return;
    }
    const helper = document.createElement("div");
    helper.className = "helperTextContainer__5a838";
    helper.dataset.appDobError = "true";
    const status = document.createElement("div");
    status.className = "statusMessageContainer__5a838";
    status.setAttribute("role", "alert");
    replaceTrustedChildren(status, `${dobErrorSvg}<div class="text-xs/normal_cf4812" id="${dobErrorId}" data-text-variant="text-xs/normal" style="color: var(--text-feedback-critical);"></div>`);
    status.querySelector(`#${dobErrorId}`).textContent = message;
    helper.appendChild(status);
    fieldsetControl.appendChild(helper);
  }

  const catalog = dateOfBirthMenuCatalog();
  const configs = Object.fromEntries(
    Object.entries(catalog).map(([key, definition]) => [key, {
      ...definition,
      combo: parts[key],
      selectedIndex: -1,
      selectedValue: null,
    }])
  );

  let openConfig = null;
  let outsidePointerHandler = null;
  let repositionHandler = null;

  function selectedIndex(config) {
    return Number.isInteger(config.selectedIndex) ? config.selectedIndex : -1;
  }

  function validCalendarDate(year, month, day) {
    const y = Number(year);
    const m = Number(month);
    const d = Number(day);
    if (!Number.isInteger(y) || !Number.isInteger(m) || !Number.isInteger(d)) return false;
    const candidate = new Date(Date.UTC(y, m - 1, d));
    return candidate.getUTCFullYear() === y && candidate.getUTCMonth() === m - 1 && candidate.getUTCDate() === d;
  }

  function syncDateState() {
    const month = configs.month.selectedValue;
    const day = configs.day.selectedValue;
    const year = configs.year.selectedValue;
    const complete = Boolean(month && day && year);
    const valid = complete && validCalendarDate(year, month, day);

    if (valid) {
      State.dateOfBirth = Object.freeze({ year, month, day });
      clearDobError();
    } else {
      State.dateOfBirth = null;

      // Selecting Month/Day/Year is not itself a validation failure. The
      // fieldset only enters its error state after the user attempts to
      // submit the registration form with an incomplete/invalid birthday.
      if (dobSubmitAttempted) {
        for (const config of Object.values(configs)) {
          config.combo.setAttribute("aria-invalid", config.selectedValue ? "false" : "true");
        }
        showDobError(complete ? "Data de nascimento inválida." : "Obrigatório");
      } else {
        clearDobError();
      }
    }
    State.status = "editing";
    return valid;
  }

  function fieldParts(config) {
    const combo = config.combo;
    const wrapper = combo.closest(".wrapper__72c38.selectField__0edde");
    const container = wrapper?.parentElement;
    const button = combo.closest(".selectButton__0edde");
    const chevron = wrapper?.querySelector(".chevronIcon__0edde");
    return { combo, wrapper, container, button, chevron };
  }

  function renderValue(config) {
    const { combo, button } = fieldParts(config);
    if (!button) return;
    const existing = button.querySelector(".placeholder__0edde, .listBoxItemContent__2e223.inInput__2e223");
    const index = selectedIndex(config);
    const selected = index >= 0 ? config.options[index] : null;
    const hiddenCurrent = combo.querySelector(".hiddenVisually_b18fe2");
    if (hiddenCurrent) hiddenCurrent.textContent = selected?.label || "";

    const next = document.createElement("div");
    if (selected) {
      next.className = "listBoxItemContent__2e223 option__56a50 inInput__2e223";
      replaceTrustedChildren(next, '<div class="lineClamp1__4bd52 text-md/normal_cf4812" data-text-variant="text-md/normal" style="color: currentcolor; grid-column: 1 / 3;"></div>');
      next.firstElementChild.textContent = selected.label;
    } else {
      next.className = "placeholder__0edde";
      replaceTrustedChildren(next, '<div class="lineClamp1__4bd52 text-md/normal_cf4812" data-text-variant="text-md/normal" style="color: currentcolor;"></div>');
      next.firstElementChild.textContent = config.placeholder;
    }

    if (existing) existing.replaceWith(next);
    else button.appendChild(next);
  }

  function positionDropdown(config) {
    if (!config.dropdown) return;
    const { wrapper } = fieldParts(config);
    if (!wrapper) return;

    const rect = wrapper.getBoundingClientRect();
    // Measure the menu in its FINAL layout size, not in its opening animation
    // scale. On the very first open the dropdown starts at scale(0.98), so
    // getBoundingClientRect().height is temporarily smaller than the final
    // menu and an above placement can overlap the select by a few pixels.
    // offsetHeight is transform-independent and includes the listbox's real
    // border/padding, which makes the first upward placement identical to
    // subsequent placements after the opening animation has settled.
    const layoutDropdownHeight = config.dropdown.offsetHeight;
    // The captured Floating UI placement leaves one var(--space-4) (4px)
    // between the select field and the floating listbox. The dropdown is a
    // sibling of the wrapper inside selectFieldContainer__0edde; it does not
    // participate in normal flow because it is position:fixed, so this
    // offset must be applied by the positioning routine itself.
    const anchorGap = 4;

    // The captured page keeps the select dropdown inside animatedDiv_b97385,
    // which has an inline transform. A transformed ancestor becomes the
    // containing block for position:fixed descendants. getBoundingClientRect()
    // is viewport-relative, while left/top on this dropdown are therefore
    // local to that transformed block. Convert the viewport coordinates back
    // to the same local coordinate system used by the original capture
    // (e.g. month ~= 32px, day ~= 188px, year ~= 323px).
    const fixedRoot = config.dropdown.closest(".animatedDiv_b97385");
    const rootRect = fixedRoot?.getBoundingClientRect();
    const scaleX = fixedRoot && fixedRoot.offsetWidth > 0 && rootRect
      ? rootRect.width / fixedRoot.offsetWidth
      : 1;
    const scaleY = fixedRoot && fixedRoot.offsetHeight > 0 && rootRect
      ? rootRect.height / fixedRoot.offsetHeight
      : 1;
    const safeScaleX = Number.isFinite(scaleX) && scaleX > 0 ? scaleX : 1;
    const safeScaleY = Number.isFinite(scaleY) && scaleY > 0 ? scaleY : 1;
    const dropdownHeight = Number.isFinite(layoutDropdownHeight) && layoutDropdownHeight > 0
      ? layoutDropdownHeight * safeScaleY
      : 242 * safeScaleY;
    const spaceBelow = window.innerHeight - rect.bottom - anchorGap;
    const spaceAbove = rect.top - anchorGap;
    const openAbove = spaceBelow < dropdownHeight && spaceAbove > spaceBelow;
    const viewportTop = openAbove
      ? Math.max(0, rect.top - dropdownHeight - anchorGap)
      : rect.bottom + anchorGap;
    const rootLeft = rootRect?.left ?? 0;
    const rootTop = rootRect?.top ?? 0;

    const localLeft = (rect.left - rootLeft) / safeScaleX;
    const localTop = (viewportTop - rootTop) / safeScaleY;
    const localWidth = rect.width / safeScaleX;

    config.dropdown.style.left = `${localLeft}px`;
    config.dropdown.style.top = `${localTop}px`;
    config.dropdown.style.minWidth = `${localWidth}px`;
    config.dropdown.style.width = `${localWidth}px`;
    config.dropdown.style.transformOrigin = openAbove ? "center bottom" : "center top";
  }

  function moveSlidingHighlight(config, option, { immediate = false } = {}) {
    SlidingHighlightController.move({ item: option, highlight: config.highlight, immediate });
  }

  function updateActive(config, index, scroll = true, immediateHighlight = false) {
    if (!config.dropdown) return;
    const count = config.options.length;
    config.activeIndex = Math.max(0, Math.min(count - 1, index));
    const options = config.dropdown.querySelectorAll('[role="option"]');
    options.forEach((option, optionIndex) => {
      const active = optionIndex === config.activeIndex;
      option.setAttribute("data-focus-visible", active ? "true" : "false");
      option.setAttribute("data-marquee-active", active ? "true" : "false");
    });
    const activeOption = options[config.activeIndex];
    if (activeOption) {
      config.combo.setAttribute("aria-activedescendant", activeOption.id);
      moveSlidingHighlight(config, activeOption, { immediate: immediateHighlight });
      if (scroll) activeOption.scrollIntoView({ block: "nearest" });
    }
  }

  function teardownGlobalDropdownListeners() {
    if (outsidePointerHandler) {
      document.removeEventListener("pointerdown", outsidePointerHandler, true);
      outsidePointerHandler = null;
    }
    if (repositionHandler) {
      window.removeEventListener("resize", repositionHandler);
      window.removeEventListener("scroll", repositionHandler, true);
      repositionHandler = null;
    }
  }

  function closeDropdown(config = openConfig, { restoreFocus = false, immediate = false } = {}) {
    if (!config) return;
    const { combo, wrapper, chevron } = fieldParts(config);
    const dropdown = config.dropdown;

    combo.setAttribute("aria-expanded", "false");
    combo.removeAttribute("aria-controls");
    combo.removeAttribute("aria-activedescendant");
    wrapper?.classList.remove("isFocused__0edde");
    chevron?.classList.remove("isOpen__0edde");
    teardownGlobalDropdownListeners();
    if (openConfig === config) openConfig = null;
    OverlayManager.release(`dob-${config.key}`);
    config.highlight = null;
    config.dropdown = null;

    if (dropdown) {
      const remove = () => dropdown.remove();
      if (immediate || typeof dropdown.animate !== "function") {
        remove();
      } else {
        const animation = dropdown.animate([
          { opacity: 1, transform: "scale(1)" },
          { opacity: 0, transform: "scale(0.98)" }
        ], { duration: 100, easing: "ease-out" });
        animation.addEventListener("finish", remove, { once: true });
      }
    }
    if (restoreFocus) combo.focus({ preventScroll: true });
  }

  function selectOption(config, index) {
    const option = config.options[index];
    if (!option) return;
    config.selectedIndex = index;
    config.selectedValue = option.value;
    config.combo.setAttribute("aria-invalid", "false");
    renderValue(config);
    syncDateState();
    closeDropdown(config, { restoreFocus: true });
  }

  function createOption(config, option, index) {
    const row = document.createElement("div");
    const selected = selectedIndex(config) === index;
    row.setAttribute("role", "option");
    row.setAttribute("tabindex", "-1");
    row.id = `${config.listId}-option-${index}`;
    row.dataset.listItemId = `${config.listId}__${row.id}`;
    row.className = "listBoxItem__2e223 row_a4ac84";
    row.setAttribute("aria-selected", selected ? "true" : "false");
    row.setAttribute("data-focus-visible", "false");
    row.setAttribute("data-marquee-active", "false");
    // The moving highlight owns the option background. Keeping each row
    // transparent prevents the CSS :hover state from jumping ahead of the
    // sliding surface while preserving text, checkmark and focus outline.
    row.style.position = "relative";
    row.style.zIndex = "1";
    row.style.backgroundColor = "transparent";
    replaceTrustedChildren(row, '<div class="listBoxItemContent__2e223 option__56a50"><div class="container_a4ac84" data-marquee-overflow="false" style="grid-column: 1 / 3;"><span class="text-sm/medium_cf4812 text_a4ac84" data-text-variant="text-sm/medium"><span class="text-md/normal_cf4812" data-text-variant="text-md/normal" style="color: currentcolor;"></span></span></div></div><div class="selectedIcon__2e223" aria-hidden="true"></div>');
    row.querySelector('.text-md\\/normal_cf4812')?.replaceChildren(document.createTextNode(option.label));
    if (selected) replaceTrustedChildren(row.querySelector(".selectedIcon__2e223"), checkmarkSvg);
    row.addEventListener("pointerenter", () => {
      if (config.activeIndex !== index) updateActive(config, index, false);
    });
    row.addEventListener("mousedown", (event) => event.preventDefault());
    row.addEventListener("click", () => selectOption(config, index));
    return row;
  }

  function openDropdown(config) {
    if (openConfig === config) return;
    if (openConfig) closeDropdown(openConfig, { immediate: true });

    const { combo, wrapper, container, chevron } = fieldParts(config);
    if (!wrapper || !container) return;
    State.status = "editing-date-of-birth";
    config.listId = `app-dob-${config.key}-list`;
    config.activeIndex = selectedIndex(config) >= 0 ? selectedIndex(config) : 0;

    const dropdown = document.createElement("div");
    dropdown.className = "selectDropdown__0edde";
    dropdown.tabIndex = -1;
    dropdown.dataset.floatingUiFocusable = "";
    dropdown.style.position = "fixed";
    dropdown.style.transitionProperty = "opacity, transform";
    dropdown.style.transitionDuration = "100ms";
    dropdown.style.opacity = "0";
    dropdown.style.transform = "scale(0.98)";

    const listbox = document.createElement("div");
    listbox.setAttribute("aria-busy", "false");
    listbox.setAttribute("role", "listbox");
    listbox.setAttribute("tabindex", "-1");
    listbox.dataset.listId = config.listId;
    listbox.setAttribute("aria-orientation", "vertical");
    listbox.setAttribute("aria-multiselectable", "false");
    listbox.className = "listBox__2e223 scrollable__2e223";
    listbox.dataset.manaComponent = "listbox";

    const scroller = document.createElement("div");
    scroller.className = "scrollbarGutterStable_d125d2 auto_d125d2 scrollerBase_d125d2";
    scroller.tabIndex = -1;
    scroller.style.overflow = "hidden scroll";
    scroller.style.height = "240px";

    const content = document.createElement("div");
    content.className = "content_d125d2";
    content.style.height = `${config.options.length * 40}px`;
    content.style.position = "relative";
    const spacer = document.createElement("div");
    spacer.setAttribute("aria-hidden", "true");
    spacer.style.height = "0px";
    content.appendChild(spacer);

    const highlight = SlidingHighlightController.ensureSingle(content, {
      attribute: "data-app-sliding-highlight",
      value: "true",
    });

    config.highlight = highlight;
    config.options.forEach((option, index) => content.appendChild(createOption(config, option, index)));
    scroller.appendChild(content);
    listbox.appendChild(scroller);
    dropdown.appendChild(listbox);
    container.appendChild(dropdown);

    config.dropdown = dropdown;
    openConfig = config;
    OverlayManager.claim({
      id: `dob-${config.key}`,
      type: "menu",
      close: (options = {}) => closeDropdown(config, { immediate: true, ...options }),
    });
    wrapper.classList.add("isFocused__0edde");
    chevron?.classList.add("isOpen__0edde");
    combo.setAttribute("aria-expanded", "true");
    combo.setAttribute("aria-controls", config.listId);
    positionDropdown(config);
    updateActive(config, config.activeIndex, true, true);

    requestAnimationFrame(() => {
      if (config.dropdown !== dropdown) return;
      dropdown.style.opacity = "1";
      dropdown.style.transform = "scale(1)";
    });

    outsidePointerHandler = (event) => {
      if (!container.contains(event.target)) closeDropdown(config);
    };
    document.addEventListener("pointerdown", outsidePointerHandler, true);
    repositionHandler = () => positionDropdown(config);
    window.addEventListener("resize", repositionHandler);
    window.addEventListener("scroll", repositionHandler, true);
  }

  function keydown(config, event) {
    const isOpen = openConfig === config;
    if (!isOpen && ["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      openDropdown(config);
      if (event.key === "ArrowUp") updateActive(config, config.options.length - 1, true);
      return;
    }
    if (!isOpen) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      updateActive(config, config.activeIndex + 1, true);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      updateActive(config, config.activeIndex - 1, true);
    } else if (event.key === "Home") {
      event.preventDefault();
      updateActive(config, 0, true);
    } else if (event.key === "End") {
      event.preventDefault();
      updateActive(config, config.options.length - 1, true);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectOption(config, config.activeIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeDropdown(config, { restoreFocus: true });
    } else if (event.key === "Tab") {
      closeDropdown(config, { immediate: true });
    }
  }

  for (const config of Object.values(configs)) {
    const { combo, wrapper, chevron } = fieldParts(config);
    if (!wrapper) continue;
    config.selectedIndex = -1;
    config.selectedValue = null;
    combo.setAttribute("aria-expanded", "false");
    combo.removeAttribute("aria-controls");
    combo.removeAttribute("aria-activedescendant");
    wrapper.classList.remove("isFocused__0edde");
    chevron?.classList.remove("isOpen__0edde");
    renderValue(config);

    // The whole select field is interactive in the captured component, not
    // only the chevron. This lets a click on the label/value area at the
    // left side open the same anchored listbox without changing HTML/CSS.
    wrapper.addEventListener("click", (event) => {
      if (event.target.closest(".chevronButton__0edde")) return;
      combo.focus({ preventScroll: true });
      if (openConfig === config) closeDropdown(config);
      else openDropdown(config);
    });
    combo.addEventListener("keydown", (event) => keydown(config, event));
    const chevronButton = wrapper.querySelector(".chevronButton__0edde");
    chevronButton?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (openConfig === config) closeDropdown(config, { restoreFocus: true });
      else {
        combo.focus({ preventScroll: true });
        openDropdown(config);
      }
    });
  }

  window.addEventListener("pagehide", () => closeDropdown(openConfig, { immediate: true }), { once: true });
  return {
    form,
    parts,
    validateForSubmit() {
      dobSubmitAttempted = true;
      const valid = syncDateState();
      if (!valid) {
        const firstMissing = Object.values(configs).find((config) => !config.selectedValue)?.combo || parts.month;
        firstMissing.focus({ preventScroll: true });
      }
      return valid;
    }
  };
}


export { wireDateOfBirth };
