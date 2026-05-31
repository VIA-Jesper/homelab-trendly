(function () {
    var STORAGE_KEY = 'aad_dismissed';
    var DAYS        = (aadSettings && aadSettings.cookieDays) ? parseInt(aadSettings.cookieDays, 10) : 30;
    var SHOW_CLOSE  = aadSettings && aadSettings.showClose === '1';

    function isDismissed() {
        try {
            var val = localStorage.getItem(STORAGE_KEY);
            if (!val) return false;
            return Date.now() < parseInt(val, 10);
        } catch (e) { return false; }
    }

    function setDismissed() {
        try {
            var expires = Date.now() + DAYS * 864e5;
            localStorage.setItem(STORAGE_KEY, expires.toString());
        } catch (e) {}
    }

    function init() {
        var bar = document.getElementById('aad-bar');
        if (!bar) return;

        if (isDismissed()) {
            bar.classList.add('aad-hidden');
            return;
        }

        document.body.classList.add('aad-active');

        if (SHOW_CLOSE) {
            var btn = bar.querySelector('.aad-close');
            if (btn) {
                btn.addEventListener('click', function () {
                    bar.classList.add('aad-hidden');
                    document.body.classList.remove('aad-active');
                    setDismissed();
                });
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
