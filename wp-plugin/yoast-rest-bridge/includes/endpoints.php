<?php
add_action( 'rest_api_init', function () {
    register_rest_route( 'yoast-bridge/v1', '/post/(?P<id>\d+)/meta', [
        [ 'methods' => 'GET',  'callback' => 'yrb_get_yoast_meta', 'permission_callback' => 'yrb_auth' ],
        [ 'methods' => 'POST', 'callback' => 'yrb_set_yoast_meta', 'permission_callback' => 'yrb_auth' ],
    ] );
} );

function yrb_auth(): bool { return current_user_can( 'edit_posts' ); }

function yrb_yoast_keys(): array {
    return [
        'focus_keyword'    => '_yoast_wpseo_focuskw',
        'meta_description' => '_yoast_wpseo_metadesc',
        'seo_title'        => '_yoast_wpseo_title',
        'canonical'        => '_yoast_wpseo_canonical',
        'schema_type'      => '_yoast_wpseo_schema_page_type',
        'no_index'         => '_yoast_wpseo_meta-robots-noindex',
    ];
}

function yrb_get_yoast_meta( WP_REST_Request $request ): WP_REST_Response {
    $post_id = (int) $request->get_param( 'id' );
    $data = [];
    foreach ( yrb_yoast_keys() as $friendly => $meta_key ) {
        $data[ $friendly ] = get_post_meta( $post_id, $meta_key, true );
    }
    return new WP_REST_Response( $data, 200 );
}

function yrb_set_yoast_meta( WP_REST_Request $request ): WP_REST_Response {
    $post_id = (int) $request->get_param( 'id' );
    $body    = $request->get_json_params();
    $updated = [];
    foreach ( yrb_yoast_keys() as $friendly => $meta_key ) {
        if ( isset( $body[ $friendly ] ) ) {
            update_post_meta( $post_id, $meta_key, sanitize_text_field( $body[ $friendly ] ) );
            $updated[ $friendly ] = $body[ $friendly ];
        }
    }
    return new WP_REST_Response( [ 'updated' => $updated ], 200 );
}
