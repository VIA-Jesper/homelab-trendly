<?php if ( ! defined( 'ABSPATH' ) ) exit; ?>

<div class="wrap">
    <h1>Affiliate Disclosure</h1>
    <p style="color:#666;max-width:640px">
        Displays a fixed top-bar disclosure on all pages, compliant with
        <strong>Markedsføringsloven §6, stk. 4</strong> (Forbrugerombudsmanden krav om
        tydelig markering <em>før</em> affiliate links).
    </p>

    <?php if ( isset( $_GET['settings-updated'] ) ): ?>
        <div class="notice notice-success is-dismissible"><p>Indstillinger gemt.</p></div>
    <?php endif; ?>

    <form method="post" action="options.php">
        <?php settings_fields( 'aad_settings_group' ); ?>

        <table class="form-table" role="presentation">

            <tr>
                <th scope="row">Aktiver disclosure</th>
                <td>
                    <label>
                        <input type="checkbox" name="aad_enabled" value="1"
                            <?php checked( aad_opt( 'enabled' ), '1' ); ?>>
                        Vis disclosure-baren på alle sider
                    </label>
                </td>
            </tr>

            <tr>
                <th scope="row"><label for="aad_text">Tekst</label></th>
                <td>
                    <textarea id="aad_text" name="aad_text" rows="3"
                        class="large-text"><?php echo esc_textarea( aad_opt( 'text' ) ); ?></textarea>
                    <p class="description">
                        Godkendte formuleringer ifølge Forbrugerombudsmanden:<br>
                        <em>"Denne side indeholder affiliate links (reklamelinks). Vi får provision ved køb."</em><br>
                        <em>"Denne side indeholder sponsoreret indhold og reklamelinks."</em>
                    </p>
                </td>
            </tr>

            <tr>
                <th scope="row"><label for="aad_bg_color">Baggrundsfarve</label></th>
                <td>
                    <input type="color" id="aad_bg_color" name="aad_bg_color"
                        value="<?php echo esc_attr( aad_opt( 'bg_color' ) ); ?>">
                    <span style="margin-left:8px;color:#666;font-size:13px">
                        Krav: høj kontrast til tekstfarven
                    </span>
                </td>
            </tr>

            <tr>
                <th scope="row"><label for="aad_text_color">Tekstfarve</label></th>
                <td>
                    <input type="color" id="aad_text_color" name="aad_text_color"
                        value="<?php echo esc_attr( aad_opt( 'text_color' ) ); ?>">
                </td>
            </tr>

            <tr>
                <th scope="row"><label for="aad_font_size">Skriftstørrelse (px)</label></th>
                <td>
                    <input type="number" id="aad_font_size" name="aad_font_size"
                        value="<?php echo esc_attr( aad_opt( 'font_size' ) ); ?>"
                        min="12" max="24" style="width:80px">
                    <p class="description">Minimum 14px anbefales (Forbrugerombudsmanden).</p>
                </td>
            </tr>

            <tr>
                <th scope="row">Luk-knap</th>
                <td>
                    <label>
                        <input type="checkbox" name="aad_show_close" value="1"
                            <?php checked( aad_opt( 'show_close' ), '1' ); ?>>
                        Vis luk-knap (huskes i 30 dage via localStorage)
                    </label>
                    <p class="description">
                        OBS: Brugere der lukker baren er stadig eksponeret ved første besøg -
                        dette er tilstrækkeligt for lovkravet.
                    </p>
                </td>
            </tr>

        </table>

        <!-- Live preview -->
        <h2 style="margin-top:24px">Preview</h2>
        <div id="aad-preview" style="
            position:relative;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:10px 48px 10px 16px;
            box-sizing:border-box;
            border-radius:4px;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            font-weight:500;
            box-shadow:0 2px 6px rgba(0,0,0,.2);
            max-width:760px;
        "></div>

        <script>
        (function () {
            var bg   = document.getElementById('aad_bg_color');
            var fg   = document.getElementById('aad_text_color');
            var txt  = document.getElementById('aad_text');
            var size = document.getElementById('aad_font_size');
            var prev = document.getElementById('aad-preview');

            function update() {
                prev.style.background = bg.value;
                prev.style.color      = fg.value;
                prev.style.fontSize   = size.value + 'px';
                prev.textContent      = txt.value;
            }

            [bg, fg, txt, size].forEach(function (el) {
                el.addEventListener('input', update);
            });
            update();
        })();
        </script>

        <?php submit_button( 'Gem indstillinger' ); ?>
    </form>
</div>
