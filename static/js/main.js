// main.js — students will add JavaScript here as features are built

document.addEventListener("DOMContentLoaded", function () {
    if (window.lucide) {
        lucide.createIcons();
    }

    // Profile date filter: "To" can never be earlier than "From".
    // Changing "From" moves the lower limit of "To", and vice versa.
    var fromInput = document.querySelector(".profile-filter-form input[name='date_from']");
    var toInput = document.querySelector(".profile-filter-form input[name='date_to']");
    if (fromInput && toInput) {
        var syncLimits = function () {
            toInput.min = fromInput.value || "";
            fromInput.max = toInput.value || "";
        };
        fromInput.addEventListener("change", syncLimits);
        toInput.addEventListener("change", syncLimits);
        syncLimits();
    }
});
