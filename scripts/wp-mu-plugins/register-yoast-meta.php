<?php
/**
 * Plugin Name: Yoast Meta REST Bridge
 * Description: Force-register Yoast SEO meta fields for REST API read/write access
 * Version: 1.1
 */

add_action('rest_api_init', function () {
    $yoast_fields = [
        '_yoast_wpseo_title',
        '_yoast_wpseo_metadesc',
        '_yoast_wpseo_focuskw',
        '_yoast_wpseo_opengraph-title',
        '_yoast_wpseo_opengraph-description',
        '_yoast_wpseo_twitter-title',
        '_yoast_wpseo_twitter-description',
        '_yoast_wpseo_primary_category',
    ];

    foreach ($yoast_fields as $field) {
        // Force register for REST even if Yoast didn't
        register_meta('post', $field, [
            'show_in_rest' => true,
            'single' => true,
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ]);

        // Also register as REST field for explicit read/write
        register_rest_field('post', $field, [
            'get_callback' => function ($post) use ($field) {
                return get_post_meta($post['id'], $field, true);
            },
            'update_callback' => function ($value, $post) use ($field) {
                update_post_meta($post->ID, $field, sanitize_text_field($value));
            },
            'schema' => [
                'type' => 'string',
                'description' => 'Yoast SEO: ' . $field,
            ],
        ]);
    }
}, 5);
