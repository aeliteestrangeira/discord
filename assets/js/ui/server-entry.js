import { OverlayManager } from "./overlay-manager.js";
import { escapeMarkup, replaceTrustedChildren } from "./dom.js";
import { emit, setButtonBusy } from "./runtime.js";

const FIRST_SERVER_TIP = "first-server";
const SKIP_ALL_TIPS = "skip-all";
const CREATE_SERVER_OVERLAY = "create-server-modal";
const STEP_HEIGHTS = Object.freeze({ templates: 560, audience: 372, customize: 418, join: 458 });

function safeLocalStorageGet(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}

function safeLocalStorageSet(key, value) {
  try { localStorage.setItem(key, value); } catch (_) {}
}

function tipKey(userId, name) {
  const id = String(userId || "unknown").trim() || "unknown";
  return `app:tips:${id}:${name}`;
}

function addServerButton() {
  return document.querySelector('[data-list-item-id="guildsnav___create-join-button"]');
}

function addServerTutorialIndicator() {
  const button = addServerButton();
  const tutorial = button?.closest(".tutorialContainer__650eb");
  return tutorial?.querySelector(".indicator_ffc7aa") || null;
}

function removeAllTutorialIndicators() {
  for (const indicator of document.querySelectorAll(".indicator_ffc7aa")) indicator.remove();
}

function overlayLayer() {
  const layers = [...document.querySelectorAll(".layerContainer__59d0d")];
  let layer = layers.reverse().find((candidate) => candidate.childElementCount === 0) || null;
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "layerContainer__59d0d";
    document.body.appendChild(layer);
  }
  return layer;
}

function tutorialMarkup() {
  return `
    <div class="clickTrapContainer__59d0d" data-app-server-tip-layer="true">
      <div id="app-first-server-tip" class="theme-dark theme-darker images-dark layer__59d0d" style="position: absolute; --reference-position-layer-max-height: 484px;">
        <div data-popout-animating="false" class="animatorRight_faf9c0 translate_faf9c0 didRender_faf9c0">
          <div class="popoutRoot__22234 contentNarrowNoMedia__22234 contentNoMedia__22234 content__22234 right__22234 arrowAlignmentTop__22234 theme-dark theme-darker images-dark" role="dialog" tabindex="-1" aria-modal="true" aria-labelledby="app-first-server-tip-title">
            <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border: 0px; clip: rect(0px, 0px, 0px, 0px); clip-path: inset(50%); height: 1px; margin: -1px; overflow: hidden; padding: 0px; position: absolute; width: 1px; white-space: nowrap;"><div role="log" aria-live="assertive" aria-relevant="additions"></div><div role="log" aria-live="polite" aria-relevant="additions"></div></div></span>
            <h1 class="titleLeft__22234 title__22234 text-md/semibold__22234" id="app-first-server-tip-title">Crie seu próprio servidor</h1>
            <div class="bodyLeft__22234 body__22234">Crie um servidor novinho com chats de voz e texto para seus amigos!</div>
            <div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="true" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
              <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button" data-app-tip-action="got-it"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Entendi!</span></div></div></button>
              <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 secondary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button" data-app-tip-action="skip-all"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Pular todas as dicas</span></div></div></button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function modalShell(stepMarkup, minHeight) {
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c">
      <div class="focusLock__49fc1" role="dialog" aria-labelledby="app-create-server-title" data-migration-pending="true" tabindex="-1" aria-modal="true">
        <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border: 0px; clip: rect(0px, 0px, 0px, 0px); clip-path: inset(50%); height: 1px; margin: -1px; overflow: hidden; padding: 0px; position: absolute; width: 1px; white-space: nowrap;"><div role="log" aria-live="assertive" aria-relevant="additions"></div><div role="log" aria-live="polite" aria-relevant="additions"></div></div></span>
        <div class="modal__024d4 root__49fc1 small__49fc1 rootWithShadow__49fc1" style="opacity: 1; transform: scale(1);">
          <div data-app-create-server-frame="true" style="position: relative; min-width: 442px; min-height: ${minHeight}px; overflow: hidden;">
            ${stepMarkup}
          </div>
        </div>
      </div>
    </div>`;
}

function templatesStepMarkup() {
  return `
    <div class="slideWrapper__024d4" data-app-create-server-step="templates" style="position: absolute; display: flex; flex-direction: column; backface-visibility: hidden; width: 442px; transform: translate3d(0px, -50%, 0px) scale(1, 1); top: 50%; left: auto; right: auto;">
      <div class="flex__7c0ba vertical_abf706 justifyStart_abf706 alignCenter_abf706 noWrap_abf706 header__49fc1 header_c04f35" id="app-create-server-title" style="flex: 0 0 auto;">
        <h1 class="defaultColor__4bd52 heading-xl/semibold_cf4812 defaultColor__5345c title_c04f35" data-text-variant="heading-xl/semibold">Crie seu servidor</h1>
        <div class="text-md/normal_cf4812 subtitle_c04f35" data-text-variant="text-md/normal" style="color: var(--text-default);">Seu servidor é onde você e seus amigos se encontram. Crie o seu e comece a conversar.</div>
        <button data-migration-pending="true" aria-label="Fechar" type="button" class="closeButton_c04f35 close__49fc1 button__201d5 lookBlank__201d5 colorBrand__201d5 grow__201d5" data-app-create-server-close="true"><div class="contents__201d5"><svg class="closeIcon__49fc1" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M17.3 18.7a1 1 0 0 0 1.4-1.4L13.42 12l5.3-5.3a1 1 0 0 0-1.42-1.4L12 10.58l-5.3-5.3a1 1 0 1 0 1.42 1.4L12 13.42l5.3 5.3Z"></path></svg></div></button>
      </div>
      <div class="content__49fc1 templatesList_c04f35 thin_d125d2 scrollerBase_d125d2" dir="ltr" data-migration-pending="true" style="overflow: hidden scroll;">
        <button class="container_eb2cd2" type="button" data-app-server-template="custom"><img class="icon_eb2cd2" alt="" src="/images/0209-b30f13ee315c2568.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Criar o meu</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <div class="text-xs/bold_cf4812 optionHeader_c04f35" data-text-variant="text-xs/bold" style="color: var(--text-default);">Começar com um modelo</div>
        <button class="container_eb2cd2" type="button" data-app-server-template="gaming"><img class="icon_eb2cd2" alt="" src="/images/0212-261f952bf028fa34.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Jogos</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-template="friends"><img class="icon_eb2cd2" alt="" src="/images/0214-d804200b134c9327.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Amigos</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-template="study_group"><img class="icon_eb2cd2" alt="" src="/images/0213-4900b53e7b34c3a5.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Grupo de estudos</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-template="school_club"><img class="icon_eb2cd2" alt="" src="/images/0215-2f1587b0c86b42e2.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Clube escolar</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-template="local_community"><img class="icon_eb2cd2" alt="" src="/images/0216-31f3db39524533b6.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Comunidade local</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-template="artists_creators"><img class="icon_eb2cd2" alt="" src="/images/0217-d8fed3f03866afe2.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Artistas e criadores</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
      </div>
      <div class="flex__7c0ba horizontalReverse__7c0ba justifyStart_abf706 alignStretch_abf706 noWrap_abf706 footer__49fc1 footer_c04f35 footerSeparator__49fc1" style="flex: 0 0 auto;">
        <h2 class="defaultColor__4bd52 heading-lg/semibold_cf4812 defaultColor__5345c footerTitle_c04f35" data-text-variant="heading-lg/semibold">Já tem um convite?</h2>
        <div data-button-hoisted-classname-wrapper="true" class="footerButton_c04f35"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 secondary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button" data-app-join-server-open="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Entrar em um servidor</span></div></div></button></div>
      </div>
    </div>`;
}

function joinServerStepMarkup(invite = "") {
  const safeInvite = escapeMarkup(invite);
  return `
    <div class="slideWrapper__024d4" data-app-create-server-step="join" style="position: absolute; display: flex; flex-direction: column; backface-visibility: hidden; width: 442px; transform: translate3d(0px, -50%, 0px) scale(1, 1); top: 50%; left: auto; right: auto;">
      <div class="flex__7c0ba vertical_abf706 justifyStart_abf706 alignCenter_abf706 noWrap_abf706 header__49fc1 header__991a0" id="app-create-server-title" style="flex: 0 0 auto;">
        <h1 class="defaultColor__4bd52 heading-xl/semibold_cf4812 defaultColor__5345c title__991a0" data-text-variant="heading-xl/semibold">Entrar em um servidor</h1>
        <div class="text-sm/normal_cf4812" data-text-variant="text-sm/normal" style="color: var(--text-default);">Digite um convite abaixo para entrar em um servidor existente</div>
        <button data-migration-pending="true" aria-label="Fechar" type="button" class="closeButton__991a0 close__49fc1 button__201d5 lookBlank__201d5 colorBrand__201d5 grow__201d5" data-app-create-server-close="true"><div class="contents__201d5"><svg class="closeIcon__49fc1" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M17.3 18.7a1 1 0 0 0 1.4-1.4L13.42 12l5.3-5.3a1 1 0 0 0-1.42-1.4L12 10.58l-5.3-5.3a1 1 0 0 0-1.4 1.42L10.58 12l-5.3 5.3a1 1 0 1 0 1.42 1.4L12 13.42l5.3 5.3Z"></path></svg></div></button>
      </div>
      <div class="content__49fc1 contentScrollbarGutter__49fc1 scrollbarGutterStable_d125d2 thin_d125d2 scrollerBase_d125d2" dir="ltr" data-migration-pending="true" style="overflow: hidden scroll;">
        <form class="inputForm__991a0" data-app-join-server-form="true"><div class="container__5a838" data-layout="vertical"><div class="labelContainer__5a838"><label class="text-md/medium_cf4812 label__5a838" aria-hidden="false" data-interactive="false" id="app-join-server-label" for="app-join-server-input" data-text-variant="text-md/medium" style="color: var(--text-strong);">Link de convite<div class="text-md/normal_cf4812 required__5a838" aria-hidden="true" data-text-variant="text-md/normal" style="color: var(--text-feedback-critical);">*</div></label></div><div class="control__5a838"><div class="container__72c38" data-full-width="false"><div class="wrapper__72c38 container__75098 md__75098 text-md/normal_cf4812" data-error="false" data-disabled="false"><input class="input__75098" aria-required="true" placeholder="https://discord.gg/hTKzmak" data-mana-component="text-input" label="Link de convite" required id="app-join-server-input" aria-invalid="false" type="text" value="${safeInvite}" name="invite-link"></div></div></div></div></form>
        <div class="text-sm/medium_cf4812" data-text-variant="text-sm/medium" style="color: var(--text-subtle);">Os convites devem ser parecidos com</div>
        <div class="sampleLinks__991a0">
          <div class="sampleLink__991a0" role="button" tabindex="0" data-app-join-sample="hTKzmak">hTKzmak</div>
          <div class="sampleLink__991a0" role="button" tabindex="0" data-app-join-sample="https://discord.gg/hTKzmak">https://discord.gg/hTKzmak</div>
          <div class="sampleLink__991a0" role="button" tabindex="0" data-app-join-sample="https://discord.gg/wumpus-friends">https://discord.gg/wumpus-friends</div>
        </div>
        <div class="rowContainer__991a0" role="button" tabindex="0" data-app-server-discovery-row="true"><img width="40" height="40" class="rowIcon__991a0" alt="" src="/images/0216-31f3db39524533b6.svg"><div><h2 class="defaultColor__4bd52 heading-md/semibold_cf4812 defaultColor__5345c rowText__991a0" data-text-variant="heading-md/semibold">Não tem um convite?</h2><div class="defaultColor__4bd52 text-xs/normal_cf4812 rowText__991a0" data-text-variant="text-xs/normal">Confira comunidades descobríveis na Descoberta de Servidores.</div></div><img class="rowArrow__991a0" alt="" src="/images/0211-050c2ac76232eff6.svg"></div>
      </div>
      <div class="flex__7c0ba horizontalReverse__7c0ba justifyStart_abf706 alignStretch_abf706 noWrap_abf706 footer__49fc1 footer__991a0 footerSeparator__49fc1" style="flex: 0 0 auto;">
        <button data-mana-component="button" role="button" aria-busy="false" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0" type="button" data-app-join-server-submit="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Entrar no servidor</span></div></div></button>
        <button data-migration-pending="true" type="button" class="button__201d5 lookLink__201d5 lowSaturationUnderline__41f68 colorPrimary__201d5 sizeMin__201d5 grow__201d5" data-app-create-server-back="templates"><div class="contents__201d5">Voltar</div></button>
      </div>
    </div>`;
}

function audienceStepMarkup() {
  // The two SVG filenames shown in the supplied DOM were not present in either
  // captured archive. Reuse the already captured Friends/Community artwork so
  // this step adds no duplicate or invented asset file.
  return `
    <div class="slideWrapper__024d4" data-app-create-server-step="audience" style="position: absolute; display: flex; flex-direction: column; backface-visibility: hidden; width: 442px; transform: translate3d(0px, -50%, 0px) scale(1, 1); top: 50%; left: auto; right: auto;">
      <div class="flex__7c0ba vertical_abf706 justifyStart_abf706 alignCenter_abf706 noWrap_abf706 header__49fc1 header__78f69" id="app-create-server-title" style="flex: 0 0 auto;">
        <h1 class="defaultColor__4bd52 heading-xl/semibold_cf4812 defaultColor__5345c title__78f69" data-text-variant="heading-xl/semibold">Conte-nos mais sobre seu servidor</h1>
        <div class="text-md/normal_cf4812 subtitle__78f69" data-text-variant="text-md/normal" style="color: var(--text-default);">Para ajudar na configuração, seu novo servidor é para apenas alguns amigos ou para uma comunidade maior?</div>
        <button data-migration-pending="true" aria-label="Fechar" type="button" class="closeButton__78f69 close__49fc1 button__201d5 lookBlank__201d5 colorBrand__201d5 grow__201d5" data-app-create-server-close="true"><div class="contents__201d5"><svg class="closeIcon__49fc1" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M17.3 18.7a1 1 0 0 0 1.4-1.4L13.42 12l5.3-5.3a1 1 0 0 0-1.42-1.4L12 10.58l-5.3-5.3a1 1 0 1 0 1.42 1.4L12 13.42l5.3 5.3Z"></path></svg></div></button>
      </div>
      <div class="content__49fc1 optionsList__78f69 thin_d125d2 scrollerBase_d125d2" dir="ltr" data-migration-pending="true" style="overflow: hidden scroll;">
        <button class="container_eb2cd2" type="button" data-app-server-audience="friends"><img class="icon_eb2cd2" alt="" src="/images/0214-d804200b134c9327.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Para mim e meus amigos</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <button class="container_eb2cd2" type="button" data-app-server-audience="community"><img class="icon_eb2cd2" alt="" src="/images/0216-31f3db39524533b6.svg"><div class="defaultColor__4bd52 text-md/bold_cf4812 text_eb2cd2" data-text-variant="text-md/bold">Para um clube ou comunidade</div><img class="arrow_eb2cd2" alt="" src="/images/0211-050c2ac76232eff6.svg"></button>
        <div class="text-sm/normal_cf4812 skip__78f69" data-text-variant="text-sm/normal" style="color: var(--text-default);">Não tem certeza? Você pode <a class="anchor_edefb8 anchorUnderlineOnHover_edefb8" role="link" tabindex="0" data-app-server-audience="skipped">pular esta pergunta</a> por enquanto.</div>
      </div>
      <div class="flex__7c0ba horizontalReverse__7c0ba justifyBetween_abf706 alignStretch_abf706 noWrap_abf706 footer__49fc1 footerSeparator__49fc1" style="flex: 0 0 auto;">
        <button data-migration-pending="true" type="button" class="backButton__78f69 button__201d5 lookBlank__201d5 colorBrand__201d5 sizeMin__201d5 grow__201d5" data-app-create-server-back="templates"><div class="contents__201d5">Voltar</div></button>
      </div>
    </div>`;
}

const UPLOAD_ICON_SVG = `<svg width="80" height="80" viewBox="0 0 80 80" fill="none" aria-hidden="true"><path fill-rule="evenodd" clip-rule="evenodd" d="M54.8694 2.85498C53.8065 2.4291 52.721 2.04752 51.6153 1.71253L51.3254 2.66957L51.0354 3.62661C51.9783 3.91227 52.9057 4.23362 53.8161 4.58911C54.1311 3.98753 54.4832 3.40847 54.8694 2.85498ZM75.4109 26.1839C76.0125 25.8689 76.5915 25.5168 77.145 25.1306C77.5709 26.1935 77.9525 27.279 78.2875 28.3847L77.3304 28.6746L76.3734 28.9646C76.0877 28.0217 75.7664 27.0943 75.4109 26.1839ZM78.8148 43.8253L79.8102 43.9222C79.9357 42.6318 80 41.3234 80 40C80 38.6766 79.9357 37.3682 79.8102 36.0778L78.8148 36.1747L77.8195 36.2715C77.9389 37.4977 78 38.7414 78 40C78 41.2586 77.9389 42.5023 77.8195 43.7285L78.8148 43.8253ZM43.8253 1.18515L43.9222 0.189853C42.6318 0.0642679 41.3234 0 40 0C38.6766 0 37.3682 0.064268 36.0778 0.189853L36.1747 1.18515L36.2715 2.18045C37.4977 2.06112 38.7414 2 40 2C41.2586 2 42.5023 2.06112 43.7285 2.18045L43.8253 1.18515ZM28.6746 2.66957L28.3847 1.71253C25.8549 2.47897 23.4312 3.48925 21.1408 4.71604L21.6129 5.59756L22.0851 6.47907C24.2606 5.3138 26.5624 4.35439 28.9646 3.62661L28.6746 2.66957ZM15.2587 9.85105L14.6239 9.0784C12.5996 10.7416 10.7416 12.5996 9.0784 14.6239L9.85105 15.2587L10.6237 15.8935C12.2042 13.9699 13.9699 12.2042 15.8935 10.6237L15.2587 9.85105ZM5.59756 21.6129L4.71604 21.1408C3.48925 23.4312 2.47897 25.8549 1.71253 28.3847L2.66957 28.6746L3.62661 28.9646C4.35439 26.5624 5.3138 24.2607 6.47907 22.0851L5.59756 21.6129ZM0 40C0 38.6766 0.0642679 37.3682 0.189853 36.0778L1.18515 36.1747L2.18045 36.2715C2.06112 37.4977 2 38.7414 2 40C2 41.2586 2.06112 42.5023 2.18045 43.7285L1.18515 43.8253L0.189853 43.9222C0.064268 42.6318 0 41.3234 0 40ZM2.66957 51.3254L1.71253 51.6153C2.47897 54.1451 3.48926 56.5688 4.71604 58.8592L5.59756 58.3871L6.47907 57.9149C5.3138 55.7394 4.35439 53.4376 3.62661 51.0354L2.66957 51.3254ZM9.85105 64.7413L9.0784 65.3761C10.7416 67.4004 12.5996 69.2584 14.6239 70.9216L15.2587 70.1489L15.8935 69.3763C13.9699 67.7958 12.2042 66.0301 10.6237 64.1065L9.85105 64.7413ZM21.6129 74.4024L21.1408 75.284C23.4312 76.5107 25.8549 77.521 28.3847 78.2875L28.6746 77.3304L28.9646 76.3734C26.5624 75.6456 24.2607 74.6862 22.0851 73.5209L21.6129 74.4024ZM36.1747 78.8148L36.0778 79.8102C37.3682 79.9357 38.6766 80 40 80C41.3234 80 42.6318 79.9357 43.9222 79.8102L43.8253 78.8148L43.7285 77.8195C42.5023 77.9389 41.2586 78 40 78C38.7414 78 37.4977 77.9389 36.2715 77.8195L36.1747 78.8148ZM51.3254 77.3304L51.6153 78.2875C54.1451 77.521 56.5688 76.5107 58.8592 75.284L58.3871 74.4024L57.9149 73.5209C55.7394 74.6862 53.4376 75.6456 51.0354 76.3734L51.3254 77.3304ZM64.7413 70.1489L65.3761 70.9216C67.4004 69.2584 69.2584 67.4004 70.9216 65.3761L70.1489 64.7413L69.3763 64.1065C67.7958 66.0301 66.0301 67.7958 64.1065 69.3763L64.7413 70.1489ZM74.4024 58.3871L75.284 58.8592C76.5107 56.5688 77.521 54.1451 78.2875 51.6153L77.3304 51.3254L76.3734 51.0354C75.6456 53.4375 74.6862 55.7393 73.5209 57.9149L74.4024 58.3871Z" fill="currentColor"></path><circle cx="68" cy="12" r="12" fill="#5865f2"></circle><path d="M73.3332 11.4075H68.5924V6.66675H67.4072V11.4075H62.6665V12.5927H67.4072V17.3334H68.5924V12.5927H73.3332V11.4075Z" fill="white"></path><path d="M40 29C37.794 29 36 30.794 36 33C36 35.207 37.794 37 40 37C42.206 37 44 35.207 44 33C44 30.795 42.206 29 40 29Z" fill="currentColor"></path><path d="M48 26.001H46.07C45.402 26.001 44.777 25.667 44.406 25.111L43.594 23.891C43.223 23.335 42.598 23 41.93 23H38.07C37.402 23 36.777 23.335 36.406 23.89L35.594 25.11C35.223 25.667 34.598 26 33.93 26H32C30.895 26 30 26.896 30 28V39C30 40.104 30.895 41 32 41H48C49.104 41 50 40.104 50 39V28C50 26.897 49.104 26.001 48 26.001ZM40 39C36.691 39 34 36.309 34 33C34 29.692 36.691 27 40 27C43.309 27 46 29.692 46 33C46 36.31 43.309 39 40 39Z" fill="currentColor"></path></svg>`;

function customizeStepMarkup(name) {
  const safeName = escapeMarkup(name);
  return `
    <div class="slideWrapper__024d4" data-app-create-server-step="customize" style="position: absolute; display: flex; flex-direction: column; backface-visibility: hidden; width: 442px; transform: translate3d(0px, -50%, 0px) scale(1, 1); top: 50%; left: auto; right: auto;">
      <div class="flex__7c0ba vertical_abf706 justifyStart_abf706 alignCenter_abf706 noWrap_abf706 header__49fc1 header_b917ac" id="app-create-server-title" style="flex: 0 0 auto;">
        <h1 class="defaultColor__4bd52 heading-xl/semibold_cf4812 defaultColor__5345c title_b917ac" data-text-variant="heading-xl/semibold">Personalize seu servidor</h1>
        <div class="text-md/normal_cf4812 subtitle_b917ac" data-text-variant="text-md/normal" style="color: var(--text-default);">Dê personalidade ao seu novo servidor com um nome e um ícone. Você sempre poderá mudar isso depois.</div>
        <button data-migration-pending="true" aria-label="Fechar" type="button" class="closeButton_b917ac close__49fc1 button__201d5 lookBlank__201d5 colorBrand__201d5 grow__201d5" data-app-create-server-close="true"><div class="contents__201d5"><svg class="closeIcon__49fc1" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M17.3 18.7a1 1 0 0 0 1.4-1.4L13.42 12l5.3-5.3a1 1 0 0 0-1.42-1.4L12 10.58l-5.3-5.3a1 1 0 1 0 1.42 1.4L12 13.42l5.3 5.3Z"></path></svg></div></button>
      </div>
      <div class="content__49fc1 contentScrollbarGutter__49fc1 createGuild_b917ac scrollbarGutterStable_d125d2 thin_d125d2 scrollerBase_d125d2" dir="ltr" data-migration-pending="true" style="overflow: hidden scroll;">
        <div class="uploadIcon_b917ac"><div class="iconContainer__98cf7">${UPLOAD_ICON_SVG}<div class="uploadLabel__98cf7" aria-hidden="true"><div class="text-xs/bold_cf4812" data-text-variant="text-xs/bold">Enviar</div></div><input class="file-input" tabindex="0" accept=".jpg,.jpeg,.jfif,.png,.gif,.webp,.avif" aria-label="Enviar um ícone do servidor" type="file" data-app-server-icon="true" style="position: absolute; top: 0px; left: 0px; width: 100%; height: 100%; opacity: 0; cursor: pointer; font-size: 0px;"></div></div>
        <form data-app-create-server-form="true"><div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-16); padding: var(--space-0);">
          <div class="container__5a838" data-layout="vertical" data-app-server-name-field="true"><div class="labelContainer__5a838"><label class="text-md/medium_cf4812 label__5a838" aria-hidden="false" data-interactive="false" id="app-server-name-label" for="app-server-name" data-text-variant="text-md/medium" style="color: var(--text-strong);">Nome do servidor<div class="text-md/normal_cf4812 required__5a838" aria-hidden="true" data-text-variant="text-md/normal" style="color: var(--text-feedback-critical);">*</div></label></div><div class="control__5a838"><div class="container__72c38" data-full-width="false"><div class="wrapper__72c38 container__75098 md__75098 text-md/normal_cf4812" data-error="false" data-disabled="false"><input class="input__75098" aria-required="true" placeholder="" maxlength="100" data-mana-component="text-input" label="Nome do servidor" required="" id="app-server-name" aria-invalid="false" type="text" value="${safeName}" name="server-name"></div></div></div></div>
          <div class="text-xs/normal_cf4812 guidelines_b917ac" data-text-variant="text-xs/normal" style="color: var(--text-muted);">Ao criar um servidor, você concorda com as <strong><a class="anchor_edefb8 anchorUnderlineOnHover_edefb8" href="https://discord.com/guidelines" rel="noreferrer noopener" target="_blank">Diretrizes da Comunidade do Discord</a></strong>.</div>
        </div></form>
      </div>
      <div class="flex__7c0ba horizontalReverse__7c0ba justifyStart_abf706 alignStretch_abf706 noWrap_abf706 footer__49fc1 footer_b917ac footerSeparator__49fc1" style="flex: 0 0 auto;">
        <button data-mana-component="button" role="button" aria-busy="false" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0" type="button" data-app-create-server-submit="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Criar</span></div></div></button>
        <button class="textButton__7a01b secondary__7a01b" data-mana-component="text-button" role="button" type="button" data-app-create-server-back="audience"><span class="lineClamp1__4bd52 text-md/medium_cf4812 text__7a01b" data-text-variant="text-md/medium">Voltar</span></button>
      </div>
    </div>`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function positionTutorialPopout(layer, anchor) {
  const popout = layer.querySelector("#app-first-server-tip");
  const root = layer.querySelector(".popoutRoot__22234");
  const animator = layer.querySelector(".translate_faf9c0");
  if (!popout || !root || !anchor?.isConnected) return;

  const rect = anchor.getBoundingClientRect();
  const width = root.offsetWidth || 280;
  const height = root.offsetHeight || 180;
  const margin = 8;
  const gap = 12;
  let placement = "right";
  let left = rect.right + gap;
  if (left + width > window.innerWidth - margin) {
    placement = "left";
    left = rect.left - width - gap;
  }
  left = clamp(left, margin, window.innerWidth - width - margin);
  const top = clamp(rect.top - 8, margin, window.innerHeight - height - margin);

  root.classList.toggle("right__22234", placement === "right");
  root.classList.toggle("left__22234", placement === "left");
  animator?.classList.toggle("animatorRight_faf9c0", placement === "right");
  animator?.classList.toggle("animatorLeft_faf9c0", placement === "left");
  popout.style.left = `${Math.round(left)}px`;
  popout.style.top = `${Math.round(top)}px`;
  popout.style.setProperty("--reference-position-layer-max-height", `${Math.max(80, window.innerHeight - top - margin)}px`);
}

function wireCapturedFirstServerModal() {
  const closeButton = document.querySelector("button.closeButton_f17563.close__49fc1");
  if (!closeButton) return;
  const layer = closeButton.closest(".layer_bc663c");
  const container = layer?.parentElement;
  if (!layer || !container) return;

  const close = () => {
    layer.remove();
    container.querySelector(":scope > .scrim__40128")?.remove();
    OverlayManager.release("captured-first-server-modal");
    emit("app:first-server-modal-closed");
  };

  OverlayManager.claim({ id: "captured-first-server-modal", type: "modal", close });
  closeButton.addEventListener("click", close, { once: true });
}

function wireTutorial(userId) {
  const indicator = addServerTutorialIndicator();
  if (!indicator) return;
  const seenKey = tipKey(userId, FIRST_SERVER_TIP);
  const skipKey = tipKey(userId, SKIP_ALL_TIPS);
  if (safeLocalStorageGet(seenKey) === "1" || safeLocalStorageGet(skipKey) === "1") {
    indicator.remove();
    return;
  }

  let activeLayer = null;
  let resizeHandler = null;
  let outsideHandler = null;
  let escapeHandler = null;

  const close = () => {
    if (resizeHandler) window.removeEventListener("resize", resizeHandler);
    if (outsideHandler) document.removeEventListener("pointerdown", outsideHandler, true);
    if (escapeHandler) document.removeEventListener("keydown", escapeHandler, true);
    activeLayer?.replaceChildren();
    OverlayManager.release("first-server-tip");
    activeLayer = null;
    resizeHandler = outsideHandler = escapeHandler = null;
  };

  const open = (event) => {
    event?.preventDefault();
    event?.stopPropagation();
    safeLocalStorageSet(seenKey, "1");
    indicator.remove();
    activeLayer = overlayLayer();
    replaceTrustedChildren(activeLayer, tutorialMarkup());
    OverlayManager.claim({ id: "first-server-tip", type: "menu", close });

    const popout = activeLayer.querySelector(".popoutRoot__22234");
    const anchor = addServerButton();
    const position = () => positionTutorialPopout(activeLayer, anchor);
    requestAnimationFrame(() => {
      position();
      popout?.focus({ preventScroll: true });
    });
    resizeHandler = position;
    window.addEventListener("resize", resizeHandler);

    outsideHandler = (pointerEvent) => {
      if (popout?.contains(pointerEvent.target)) return;
      close();
    };
    document.addEventListener("pointerdown", outsideHandler, true);
    escapeHandler = (keyEvent) => {
      if (keyEvent.key !== "Escape") return;
      keyEvent.preventDefault();
      close();
    };
    document.addEventListener("keydown", escapeHandler, true);

    activeLayer.querySelector('[data-app-tip-action="got-it"]')?.addEventListener("click", close, { once: true });
    activeLayer.querySelector('[data-app-tip-action="skip-all"]')?.addEventListener("click", () => {
      safeLocalStorageSet(skipKey, "1");
      removeAllTutorialIndicators();
      close();
      emit("app:tutorials-skipped");
    }, { once: true });
    emit("app:first-server-tip-opened");
  };

  indicator.addEventListener("click", open, { once: true });
  indicator.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") open(event);
  });
}

function showFieldError(field, message) {
  if (!field) return;
  const control = field.querySelector(".control__5a838");
  const wrapper = field.querySelector(".wrapper__72c38.container__75098");
  const input = field.querySelector("input.input__75098");
  if (!control || !wrapper || !input) return;
  wrapper.dataset.error = "true";
  input.setAttribute("aria-invalid", "true");
  let helper = control.querySelector('[data-app-server-field-error="true"]');
  if (!helper) {
    helper = document.createElement("div");
    helper.className = "helperTextContainer__5a838";
    helper.dataset.appServerFieldError = "true";
    replaceTrustedChildren(helper, '<div class="statusMessageContainer__5a838" role="alert"><svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent"></circle><path fill="var(--text-feedback-critical)" fill-rule="evenodd" d="M12 23a11 11 0 1 0 0-22 11 11 0 0 0 0 22Zm1.44-15.94L13.06 14a1.06 1.06 0 0 1-2.12 0l-.38-6.94a1 1 0 0 1 1-1.06h.88a1 1 0 0 1 1 1.06Zm-.19 10.69a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" clip-rule="evenodd"></path></svg><div class="text-xs/normal_cf4812" data-text-variant="text-xs/normal" style="color: var(--text-feedback-critical);"></div></div>');
    control.appendChild(helper);
  }
  helper.querySelector(".text-xs\\/normal_cf4812").textContent = String(message || "Não foi possível criar o servidor.");
}

function clearFieldError(field) {
  if (!field) return;
  field.querySelector(".wrapper__72c38.container__75098")?.setAttribute("data-error", "false");
  field.querySelector("input.input__75098")?.setAttribute("aria-invalid", "false");
  field.querySelector('[data-app-server-field-error="true"]')?.remove();
}

function animateStep(slide, direction) {
  if (!slide || typeof slide.animate !== "function" || window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;
  const offset = direction === "back" ? -42 : 42;
  slide.animate([
    { transform: `translate3d(${offset}px, -50%, 0px) scale(0.985, 0.985)`, opacity: 0.72 },
    { transform: "translate3d(0px, -50%, 0px) scale(1, 1)", opacity: 1 },
  ], { duration: 190, easing: "cubic-bezier(0.2, 0, 0, 1)" });
}

function wireCreateServerModal(authProvider, user) {
  const button = addServerButton();
  if (!button) return;
  const userId = String(user?.id || "").trim();
  const username = String(user?.username || "usuário").trim().toLowerCase() || "usuário";

  const open = (event) => {
    event?.preventDefault();
    event?.stopPropagation();
    safeLocalStorageSet(tipKey(userId, FIRST_SERVER_TIP), "1");
    addServerTutorialIndicator()?.remove();

    const layer = overlayLayer();
    const state = {
      step: "templates",
      templateKey: "custom",
      audience: "friends",
      name: `${username}'s server`,
      icon: null,
      joinInvite: "",
      busy: false,
    };
    replaceTrustedChildren(layer, modalShell(templatesStepMarkup(), STEP_HEIGHTS.templates));
    let keydown = null;

    const close = () => {
      if (state.busy) return;
      if (keydown) document.removeEventListener("keydown", keydown, true);
      keydown = null;
      layer.replaceChildren();
      OverlayManager.release(CREATE_SERVER_OVERLAY);
      emit("app:create-server-modal-closed");
    };

    const render = (step, direction = "forward") => {
      state.step = step;
      const frame = layer.querySelector('[data-app-create-server-frame="true"]');
      if (!frame) return;
      if (step === "templates") replaceTrustedChildren(frame, templatesStepMarkup());
      else if (step === "audience") replaceTrustedChildren(frame, audienceStepMarkup());
      else if (step === "join") replaceTrustedChildren(frame, joinServerStepMarkup(state.joinInvite));
      else replaceTrustedChildren(frame, customizeStepMarkup(state.name));
      frame.style.minHeight = `${STEP_HEIGHTS[step]}px`;
      const slide = frame.querySelector(".slideWrapper__024d4");
      animateStep(slide, direction);
      wireStep();
      requestAnimationFrame(() => {
        const target = step === "customize"
          ? frame.querySelector("#app-server-name")
          : step === "join"
            ? frame.querySelector("#app-join-server-input")
            : layer.querySelector(".focusLock__49fc1");
        target?.focus({ preventScroll: true });
      });
      emit("app:create-server-step", { step, templateKey: state.templateKey, audience: state.audience });
    };

    const wireStep = () => {
      layer.querySelector('[data-app-create-server-close="true"]')?.addEventListener("click", close, { once: true });
      if (state.step === "templates") {
        layer.querySelector('[data-app-join-server-open="true"]')?.addEventListener("click", () => render("join", "forward"), { once: true });
        for (const option of layer.querySelectorAll("[data-app-server-template]")) {
          option.addEventListener("click", () => {
            state.templateKey = String(option.dataset.appServerTemplate || "custom");
            render("audience", "forward");
          }, { once: true });
        }
        return;
      }
      if (state.step === "join") {
        const inviteInput = layer.querySelector("#app-join-server-input");
        const joinForm = layer.querySelector('[data-app-join-server-form="true"]');
        layer.querySelector('[data-app-create-server-back="templates"]')?.addEventListener("click", () => {
          state.joinInvite = inviteInput?.value || state.joinInvite;
          render("templates", "back");
        }, { once: true });
        joinForm?.addEventListener("submit", (event) => event.preventDefault());
        inviteInput?.addEventListener("input", () => { state.joinInvite = inviteInput.value; });
        for (const sample of layer.querySelectorAll("[data-app-join-sample]")) {
          const chooseSample = (event) => {
            event?.preventDefault();
            if (!inviteInput) return;
            state.joinInvite = String(sample.dataset.appJoinSample || "");
            inviteInput.value = state.joinInvite;
            inviteInput.focus({ preventScroll: true });
            emit("app:join-server-sample-selected");
          };
          sample.addEventListener("click", chooseSample);
          sample.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") chooseSample(event);
          });
        }
        return;
      }
      if (state.step === "audience") {
        layer.querySelector('[data-app-create-server-back="templates"]')?.addEventListener("click", () => render("templates", "back"), { once: true });
        for (const option of layer.querySelectorAll("[data-app-server-audience]")) {
          const choose = (event) => {
            event?.preventDefault();
            state.audience = String(option.dataset.appServerAudience || "skipped");
            render("customize", "forward");
          };
          option.addEventListener("click", choose, { once: true });
          if (option.tagName === "A") option.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") choose(event);
          });
        }
        return;
      }

      const field = layer.querySelector('[data-app-server-name-field="true"]');
      const input = layer.querySelector("#app-server-name");
      const fileInput = layer.querySelector('[data-app-server-icon="true"]');
      const submit = layer.querySelector('[data-app-create-server-submit="true"]');
      const back = layer.querySelector('[data-app-create-server-back="audience"]');
      if (!input || !submit) return;

      const syncSubmit = () => {
        state.name = input.value;
        submit.disabled = state.busy || state.name.trim().length === 0;
      };
      syncSubmit();
      input.addEventListener("input", () => {
        clearFieldError(field);
        syncSubmit();
      });
      fileInput?.addEventListener("change", () => {
        const chosen = fileInput.files?.[0] || null;
        state.icon = chosen;
        clearFieldError(field);
      });
      back?.addEventListener("click", () => {
        if (state.busy) return;
        state.name = input.value;
        render("audience", "back");
      }, { once: true });
      submit.addEventListener("click", async () => {
        if (state.busy) return;
        state.name = input.value.trim();
        if (!state.name) {
          showFieldError(field, "O nome do servidor é obrigatório.");
          syncSubmit();
          return;
        }
        if (state.icon && state.icon.size > 8 * 1024 * 1024) {
          showFieldError(field, "A imagem do servidor é muito grande.");
          return;
        }
        state.busy = true;
        submit.disabled = true;
        back && (back.disabled = true);
        input.disabled = true;
        if (fileInput) fileInput.disabled = true;
        setButtonBusy(submit, true);
        clearFieldError(field);
        try {
          const result = await authProvider.createGuild({
            name: state.name,
            templateKey: state.templateKey,
            audience: state.audience,
            icon: state.icon,
          });
          if (result?.error || !result?.data?.redirect) {
            showFieldError(field, result?.error?.message || "Não foi possível criar o servidor agora.");
            return;
          }
          emit("app:guild-created", { guildId: result.data.guild?.id || "", templateKey: state.templateKey, audience: state.audience });
          location.assign(result.data.redirect);
        } catch (_) {
          showFieldError(field, "Não foi possível criar o servidor agora.");
        } finally {
          if (document.contains(submit)) {
            state.busy = false;
            setButtonBusy(submit, false);
            input.disabled = false;
            if (fileInput) fileInput.disabled = false;
            if (back) back.disabled = false;
            syncSubmit();
          }
        }
      });
    };

    OverlayManager.claim({ id: CREATE_SERVER_OVERLAY, type: "modal", close });
    layer.querySelector(":scope > .scrim__40128")?.addEventListener("click", close);
    keydown = (keyEvent) => {
      if (keyEvent.key !== "Escape") return;
      keyEvent.preventDefault();
      close();
    };
    document.addEventListener("keydown", keydown, true);
    wireStep();
    requestAnimationFrame(() => layer.querySelector(".focusLock__49fc1")?.focus({ preventScroll: true }));
    emit("app:create-server-modal-opened");
  };

  button.addEventListener("click", open);
  button.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") open(event);
  });
}

export function wireServerEntry(authProvider, user) {
  wireCapturedFirstServerModal();
  const userId = String(user?.id || "").trim();
  wireTutorial(userId);
  wireCreateServerModal(authProvider, user);
}
