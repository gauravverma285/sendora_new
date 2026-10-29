/**
 * WEBSITE: https://themefisher.com
 * TWITTER: https://twitter.com/themefisher
 * FACEBOOK: https://www.facebook.com/themefisher
 * GITHUB: https://github.com/themefisher/
 */

// Preloader js
$(window).on("load", function () {
  "use strict";
  $(".preloader").fadeOut(0);
});

(function ($) {
  "use strict";

  // tab
  $(".tab-content")
    .find(".tab-pane")
    .each(function (idx, item) {
      var navTabs = $(this).closest(".code-tabs").find(".nav-tabs"),
        title = $(this).attr("title");
      navTabs.append(
        '<li class="nav-item"><a class="nav-link" href="#">' +
          title +
          "</a></li>"
      );
    });

  $(".code-tabs ul.nav-tabs").each(function () {
    $(this).find("li:first").addClass("active");
  });

  $(".code-tabs .tab-content").each(function () {
    $(this).find("div:first").addClass("active");
  });

  $(".nav-tabs a").click(function (e) {
    e.preventDefault();
    var tab = $(this).parent(),
      tabIndex = tab.index(),
      tabPanel = $(this).closest(".code-tabs"),
      tabPane = tabPanel.find(".tab-pane").eq(tabIndex);
    tabPanel.find(".active").removeClass("active");
    tab.addClass("active");
    tabPane.addClass("active");
  });

  // accordion-collapse
  $(".accordion-collapse").on("show.bs.collapse", function () {
    $(this).siblings(".accordion-header").addClass("active");
  });
  $(".accordion-collapse").on("hide.bs.collapse", function () {
    $(this).siblings(".accordion-header").removeClass("active");
  });

  //post slider
  $(".post-slider").slick({
    slidesToShow: 1,
    slidesToScroll: 1,
    autoplay: true,
    autoplaySpeed: 4500,
    dots: false,
    arrows: true,
    prevArrow:
      '<button type="button" class="prevArrow"><i class="fas fa-angle-left"></i></button>',
    nextArrow:
      '<button type="button" class="nextArrow"><i class="fas fa-angle-right"></i></button>',
  });

  // videoPopupInit
  function videoPopupInit() {
    var $videoSrc;
    $(".video-play-btn").click(function () {
      $videoSrc = $(this).data("src");
    });
    $("#videoModal").on("shown.bs.modal", function (e) {
      $("#showVideo").attr(
        "src",
        $videoSrc + "?autoplay=1&amp;modestbranding=1&amp;showinfo=0"
      );
    });
    $("#videoModal").on("hide.bs.modal", function (e) {
      $("#showVideo").attr("src", $videoSrc);
    });
  }
  videoPopupInit();

  // table of content
  new ScrollMenu("#TableOfContents a", {
    duration: 400,
    activeOffset: 40,
    scrollOffset: 10,
  });
})(jQuery);

// Bootstrap tooltips/popovers require manual initialization
document.addEventListener("DOMContentLoaded", function () {
  if (typeof bootstrap === "undefined") return;
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
    new bootstrap.Popover(el);
  });
});

// Shared button-loading helper — used by any page that fires a fetch()
// request from a button click, so there's always visible feedback instead
// of a button that looks inert while a request is in flight (and inviting
// a second click).
window.AppLoading = {
  start(btn, label) {
    if (!btn || btn.dataset.loading === "1") return;
    btn.dataset.loading = "1";
    btn.dataset.originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.classList.add("is-loading");
    btn.innerHTML = `<span class="au-spinner"></span> ${label || "Please wait…"}`;
  },
  stop(btn) {
    if (!btn || btn.dataset.loading !== "1") return;
    btn.disabled = false;
    btn.classList.remove("is-loading");
    btn.innerHTML = btn.dataset.originalHtml || btn.innerHTML;
    delete btn.dataset.loading;
    delete btn.dataset.originalHtml;
  },
};

// Auto-dismiss Django message toasts after a while
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("#auToastStack .au-toast").forEach(function (toast) {
    setTimeout(function () {
      toast.style.transition = "opacity .3s ease";
      toast.style.opacity = "0";
      setTimeout(function () { toast.remove(); }, 300);
    }, 7000);
  });
});

// Focus the app search box with Ctrl+K / Cmd+K
document.addEventListener("keydown", function (e) {
  const searchInput = document.getElementById("appSearchInput");
  if (!searchInput) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    searchInput.focus();
  }
});

// App search: quick jump to a feature/page, with a "no results" state
document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("appSearchInput");
  const resultsBox = document.getElementById("appSearchResults");
  const dataEl = document.getElementById("appSearchData");
  if (!searchInput || !resultsBox || !dataEl) return;

  let items = [];
  try {
    items = JSON.parse(dataEl.textContent);
  } catch (err) {
    console.error("Could not parse app search data:", err);
  }

  function renderResults(query) {
    const q = query.trim().toLowerCase();
    const matches = q
      ? items.filter(item => item.label.toLowerCase().includes(q))
      : items;

    resultsBox.innerHTML = "";

    if (matches.length === 0) {
      const empty = document.createElement("div");
      empty.className = "app-search__empty";
      empty.textContent = `No results found for "${query}"`;
      resultsBox.appendChild(empty);
      return;
    }

    matches.forEach(item => {
      const link = document.createElement("a");
      link.className = "app-search__result";
      link.href = item.url;
      link.innerHTML = `<i class="mdi ${item.icon}"></i><span>${item.label}</span>`;
      resultsBox.appendChild(link);
    });
  }

  searchInput.addEventListener("focus", function () {
    renderResults(searchInput.value);
    resultsBox.hidden = false;
  });

  searchInput.addEventListener("input", function () {
    renderResults(searchInput.value);
    resultsBox.hidden = false;
  });

  document.addEventListener("click", function (e) {
    if (!searchInput.contains(e.target) && !resultsBox.contains(e.target)) {
      resultsBox.hidden = true;
    }
  });

  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      resultsBox.hidden = true;
      searchInput.blur();
    }
  });
});
