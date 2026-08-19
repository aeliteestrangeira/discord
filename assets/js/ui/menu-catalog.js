const monthLabels = Object.freeze([
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]);

export function dateOfBirthMenuCatalog(currentYear = new Date().getFullYear()) {
  return Object.freeze({
    month: Object.freeze({
      key: "month",
      ariaLabel: "Mês",
      placeholder: "Mês",
      options: Object.freeze(monthLabels.map((label, index) => Object.freeze({
        label,
        value: String(index + 1).padStart(2, "0"),
      }))),
    }),
    day: Object.freeze({
      key: "day",
      ariaLabel: "Dia",
      placeholder: "Dia",
      options: Object.freeze(Array.from({ length: 31 }, (_, index) => Object.freeze({
        label: String(index + 1),
        value: String(index + 1).padStart(2, "0"),
      }))),
    }),
    year: Object.freeze({
      key: "year",
      ariaLabel: "Ano",
      placeholder: "Ano",
      options: Object.freeze(Array.from({ length: 101 }, (_, index) => Object.freeze({
        label: String(currentYear - index),
        value: String(currentYear - index),
      }))),
    }),
  });
}
