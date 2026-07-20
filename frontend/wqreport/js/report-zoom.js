function fitReportsToViewport() {
  const viewport = document.querySelector(".reports-viewport");
  const wrapper = document.getElementById("reports-scale-wrapper");
  const reports = document.getElementById("reports");
  const firstPage = document.querySelector(".report-page");

  if (!viewport || !wrapper || !reports || !firstPage) {
    return;
  }

  const viewportStyle = window.getComputedStyle(viewport);
  const paddingLeft = parseFloat(viewportStyle.paddingLeft) || 0;
  const paddingRight = parseFloat(viewportStyle.paddingRight) || 0;
  const availableWidth = viewport.clientWidth - paddingLeft - paddingRight;
  const pageWidth = firstPage.offsetWidth;

  if (!pageWidth || !availableWidth) {
    return;
  }

  const scale = availableWidth / pageWidth;
  const scaledWidth = pageWidth * scale;
  const scaledHeight = reports.scrollHeight * scale;

  wrapper.style.setProperty("--report-scale", scale);
  wrapper.style.width = `${scaledWidth}px`;
  wrapper.style.height = `${scaledHeight}px`;
  wrapper.style.transform = "none";

  reports.style.width = `${pageWidth}px`;
  reports.style.transform = `scale(${scale})`;
  reports.style.transformOrigin = "top left";
}

let pendingFitFrame = 0;

function scheduleReportsFit() {
  if (pendingFitFrame) return;
  pendingFitFrame = requestAnimationFrame(() => {
    pendingFitFrame = 0;
    fitReportsToViewport();
  });
}

window.addEventListener("resize", scheduleReportsFit);
window.addEventListener("load", scheduleReportsFit);

document.addEventListener("DOMContentLoaded", () => {
  scheduleReportsFit();

  const reports = document.getElementById("reports");

  if (reports) {
    const observer = new MutationObserver(scheduleReportsFit);

    observer.observe(reports, {
      childList: true,
      subtree: true
    });
  }
});
