import { formatDateShort } from "./utils.js";

const preferencesKey = "agender.reports.water-quality.preferences";
let policyProfile = readPolicyProfile();

export function getStoredPolicyProfile() {
  return policyProfile;
}

export function updatePolicyHeaders(root = document) {
  const pages = root.matches?.(".report-page")
    ? [root]
    : Array.from(root.querySelectorAll(".report-page"));
  const allPages = Array.from(document.querySelectorAll(".report-page"));

  pages.forEach((page, index) => {
    const dateInput = page.querySelector(".report-date-input");
    const dateValue = page.querySelector(".ti-header-date-value");
    const pageValue = page.querySelector(".ti-header-page-value");
    const pageIndex = allPages.indexOf(page);

    if (dateValue) {
      dateValue.textContent = formatDateShort(dateInput?.value || "");
    }

    if (pageValue) {
      pageValue.textContent = `Página ${pageIndex + 1} de ${allPages.length}`;
    }
  });
}

export function applyPolicyProfile(profile = getStoredPolicyProfile(), select = null) {
  document.body.dataset.policyProfile = profile;

  const reports = document.getElementById("reports");

  if (reports) {
    reports.dataset.policyProfile = profile;
  }

  if (select) {
    select.value = profile;
  }

  updatePolicyHeaders();
}

export function savePolicyProfile(profile, select = null) {
  policyProfile = ["default", "it"].includes(profile) ? profile : "default";
  applyPolicyProfile(policyProfile, select);
}

function readPolicyProfile() {
  const stored = (
    window.parent?.NotasWaterQualitySession?.initialPreferences
    || window.parent?.NotasStorage?.loadJson(preferencesKey, null)
  )?.policy;
  return ["default", "it"].includes(stored) ? stored : "default";
}
