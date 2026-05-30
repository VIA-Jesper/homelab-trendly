<?php
/**
 * Register Yoast SEO meta fields with the WP REST API.
 *
 * By default Yoast does not expose its post meta to the REST API, so
 * POST /wp-json/wp/v2/posts with a "meta" block containing Yoast keys
 * is silently ignored. This mu-plugin registers the three fields the
 * pipeline sets so they are writable via the REST API.
 *
 * Install: copy to wp-content/mu-plugins/register-yoast-meta.php
 * No activation needed — mu-plugins load automatically.
 */

add_action( 'init', function () {
    $fields = [
        '_yoast_wpseo_title',
        '_yoast_wpseo_metadesc',
        '_yoast_wpseo_focuskw',
    ];

    foreach ( $fields as $key ) {
        register_meta( 'post', $key, [
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => 'string',
            'auth_callback' => function () {
                return current_user_can( 'edit_posts' );
            },
        ] );
    }
} );
