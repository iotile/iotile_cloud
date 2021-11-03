$(document).ready(function () {

    /* ======== OFFCANVAS MOBILE MENU ACTION ======== */
    var $btnOffcanvasOpen = $('.offcanvas__toggle');
    var $sideNav = $('.offcanvas');
    var $bodyOverflow = $('body');
    var $contentWrapper = $('.content-wrapper');

    $btnOffcanvasOpen.on('click', function (event) {
        event.preventDefault();
        $(this).toggleClass('active');
        $sideNav.toggleClass('open');
        $bodyOverflow.toggleClass('offcanvas-open');
        $contentWrapper.toggleClass('open');
    });
    $('.offcanvas__close').on('click', function (e) {
        e.preventDefault();
        $btnOffcanvasOpen.removeClass('active');
        $sideNav.removeClass('open');
        $bodyOverflow.removeClass('offcanvas-open');
        $contentWrapper.removeClass('open');
    });

    /* ======== SLICK CAROUSEL INITIAL ======== */
    $('.carousel-hero').slick({
        autoplay: true,
        autoplaySpeed: 5000,
        arrows: false,
        draggable: false,
        fade: true,
        pauseOnFocus: false,
        pauseOnHover: false,
        swipe: false,
        touchMove: false,
        speed: 1200
    });

    $('.carousel-location').slick({
        autoplay: true,
        autoplaySpeed: 25000,
        arrows: false,
        dots: true,
        pauseOnFocus: false,
        pauseOnHover: false,
        speed: 1200
    });

    /* ======== SCROLL TO ACTION ======== */
    $('[data-click=scroll-to-target]').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        $btnOffcanvasOpen.removeClass('active');
        $sideNav.removeClass('open');
        $bodyOverflow.removeClass('offcanvas-open');
        $contentWrapper.removeClass('open');
        var target = $(this).attr('href');
        $('html, body').animate({
            scrollTop: $(target).offset().top
        }, 500);
    });

});
