// Find a Mentor inside the website page. The cards are already in the page,
// placed there as it was served. This script does two things:
//  - shuffles the cards each time the page opens, so the same mentors are
//    not always first (Doug, 11-16-26). It runs in the visitor's browser
//    because any cache between here and the visitor would freeze a
//    server-side order;
//  - hides the cards that do not match the search, using the chapter
//    applications' search over the whole profile (ruling 33, WT-46).
(function () {
  var root = document.querySelector("[data-cmw-search]");
  if (!root) return;
  var grid = root.querySelector(".cmw-grid");
  var input = root.querySelector(".cmw-search__input");
  var none = root.querySelector(".cmw-search__none");
  var cards = Array.prototype.slice.call(root.querySelectorAll(".cmw-card"));

  function slugOf(card) {
    var slug = card.getAttribute("data-cmw-slug");
    if (slug) return slug;
    var link = card.querySelector(".cmw-card__link");
    return link ? link.getAttribute("href").split("/").filter(Boolean).pop() : "";
  }

  // Fisher–Yates, then put the cards back in the new order.
  for (var i = cards.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var t = cards[i]; cards[i] = cards[j]; cards[j] = t;
  }
  if (grid) cards.forEach(function (card) { grid.appendChild(card); });

  function showAll() {
    cards.forEach(function (c) { c.hidden = false; });
    if (none) none.hidden = true;
  }

  if (!input) return;
  var timer;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (!input.value.trim()) { showAll(); return; }
      fetch(root.getAttribute("data-cmw-search") + "?q=" + encodeURIComponent(input.value))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          var shown = 0;
          cards.forEach(function (card) {
            card.hidden = res.slugs.indexOf(slugOf(card)) === -1;
            if (!card.hidden) shown++;
          });
          if (none) none.hidden = shown > 0;
        })
        .catch(showAll);
    }, 200);
  });
})();
