<?php
/**
 * Plugin Name:  Auto Affiliate Disclosure
 * Description:  Fixed top-bar affiliate disclosure compliant with Danish Markedsføringsloven §6, stk. 4.
 * Version:      1.0.0
 * Author:       Trendly
 * License:      GPL-2.0+
 * Text Domain:  auto-affiliate-disclosure
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'AAD_VERSION',    '1.0.0' );
define( 'AAD_DIR',        plugin_dir_path( __FILE__ ) );
define( 'AAD_URL',        plugin_dir_url( __FILE__ ) );

// ── Defaults ─────────────────────────────────────────────────────────────────

function aad_defaults(): array {
    return [
        'enabled'    => '1',
        'text'       => 'Denne side indeholder affiliate links (reklamelinks). Vi får provision ved køb.',
        'bg_color'   => '#1a1a1a',
        'text_color' => '#ffffff',
        'font_size'  => '14',
        'show_close' => '1',
    ];
}

function aad_opt( string $key ): string {
    return (string) get_option( 'aad_' . $key, aad_defaults()[ $key ] ?? '' );
}

// ── Settings registration ─────────────────────────────────────────────────────

add_action( 'admin_init', function () {
    foreach ( array_keys( aad_defaults() ) as $field ) {
        register_setting( 'aad_settings_group', 'aad_' . $field, [
            'sanitize_callback' => 'sanitize_text_field',
        ] );
    }
} );

// ── Admin menu ────────────────────────────────────────────────────────────────

add_action( 'admin_menu', function () {
    add_options_page(
        'Affiliate Disclosure',
        'Affiliate Disclosure',
        'manage_options',
        'auto-affiliate-disclosure',
        function () {
            include AAD_DIR . 'assets/admin/settings-page.php';
        }
    );
} );

// ── Frontend assets ───────────────────────────────────────────────────────────

add_action( 'wp_enqueue_scripts', function () {
    if ( aad_opt( 'enabled' ) !== '1' ) return;

    wp_enqueue_style(
        'aad-disclosure',
        AAD_URL . 'assets/css/disclosure.css',
        [],
        AAD_VERSION
    );

    wp_enqueue_script(
        'aad-disclosure',
        AAD_URL . 'assets/js/disclosure.js',
        [],
        AAD_VERSION,
        true   // load in footer
    );

    wp_localize_script( 'aad-disclosure', 'aadSettings', [
        'showClose'  => aad_opt( 'show_close' ),
        'cookieDays' => 30,
    ] );
} );

// ── Output the bar ────────────────────────────────────────────────────────────

function aad_render_bar(): void {
    if ( aad_opt( 'enabled' ) !== '1' ) return;

    $bg         = esc_attr( aad_opt( 'bg_color' ) );
    $color      = esc_attr( aad_opt( 'text_color' ) );
    $size       = max( 12, absint( aad_opt( 'font_size' ) ) );
    $text       = esc_html( aad_opt( 'text' ) );
    $show_close = aad_opt( 'show_close' ) === '1';

    printf(
        '<div id="aad-bar" style="background:%s;color:%s;font-size:%dpx" role="complementary" aria-label="Affiliate oplysning">',
        $bg, $color, $size
    );
    echo '<span class="aad-text">' . $text . '</span>';
    if ( $show_close ) {
        echo '<button class="aad-close" aria-label="Luk besked" title="Luk">&times;</button>';
    }
    echo '</div>';
}

// Primary hook: wp_body_open (WP 5.2+, requires theme support)
add_action( 'wp_body_open', 'aad_render_bar' );

// Fallback: inject via JavaScript for themes without wp_body_open
add_action( 'wp_footer', function () {
    if ( aad_opt( 'enabled' ) !== '1' ) return;
    if ( did_action( 'wp_body_open' ) ) return; // already rendered
    ?>
    <script>
    (function () {
        var bar = document.getElementById('aad-bar');
        if (bar) { document.body.prepend(bar); }
    })();
    </script>
    <?php
} );
