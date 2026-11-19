(function () {
    'use strict';

    function initVendaAdmin($) {
        function formatMoney(num) {
            return (num || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function parseNum(val) {
            if (!val) return 0;
            if (typeof val === 'number') return val;
            var clean = String(val).replace(/\s/g, '');
            if (clean.indexOf(',') > -1 && clean.indexOf('.') > -1) {
                clean = clean.replace(/\./g, '').replace(',', '.');
            } else if (clean.indexOf(',') > -1) {
                clean = clean.replace(',', '.');
            }
            return parseFloat(clean) || 0;
        }

        var lastTotals = { subtotal: 0, desconto: 0, total: 0 };

        // --- 1. AUTO-PREENCHIMENTO DO VALOR UNITÁRIO AO SELECIONAR PRODUTO (MANTENDO EDITÁVEL) ---
        $(document).on('change', 'select[name$="-produto"]', function () {
            var $select = $(this);
            var prodId = $select.val();
            if (!prodId) return;

            var $row = $select.closest('tr.form-row, .inline-related');
            var $unitInput = $row.find('input[name$="-valor_unitario"]');
            if (!$unitInput.length) return;

            var url = '/admin/vendas/venda/preco-produto/' + prodId + '/';
            $.getJSON(url, function (data) {
                if (data && data.preco_venda !== undefined) {
                    $unitInput.val(Number(data.preco_venda).toFixed(2));
                    calcularTotais();
                }
            });
        });

        // --- 2. CÁLCULO AUTOMÁTICO DE SUBTOTAL E TOTAL EM TEMPO REAL ---
        function calcularTotais() {
            var subtotal = 0;

            $('tr.form-row, .tabular.inline-related tbody tr').each(function () {
                var $row = $(this);
                if ($row.hasClass('empty-form')) return;

                var isDeleted = $row.find('.field-DELETE input:checked, input[name$="-DELETE"]:checked').length > 0;
                if (isDeleted) return;

                var $qtdEl = $row.find('[name$="-quantidade"]');
                if (!$qtdEl.length) return;

                var qtd = parseNum($qtdEl.val());
                var unit = parseNum($row.find('[name$="-valor_unitario"]').val());
                var descUnit = parseNum($row.find('[name$="-desconto_unitario"]').val());
                var rowTotal = Math.max(0, qtd * (unit - descUnit));

                var $rowTotalDisplay = $row.find('.field-valor_total .readonly, .field-valor_total p');
                if ($rowTotalDisplay.length) {
                    $rowTotalDisplay.text(formatMoney(rowTotal));
                }

                subtotal += rowTotal;
            });

            if (!$('[name$="-quantidade"]').length) {
                subtotal = parseNum($('.field-subtotal .readonly, .field-subtotal p').first().text());
            }

            var desc = $('#id_desconto').length
                ? parseNum($('#id_desconto').val())
                : parseNum($('.field-desconto .readonly, .field-desconto p').first().text());
            var totalGeral = Math.max(0, subtotal - desc);

            lastTotals = { subtotal: subtotal, desconto: desc, total: totalGeral };

            $('.field-subtotal .readonly, .field-subtotal p').text(formatMoney(subtotal));
            $('.field-valor_total .readonly, .field-valor_total p').text(formatMoney(totalGeral));
        }

        $(document).on(
            'input change keyup',
            '[name$="-quantidade"], [name$="-valor_unitario"], [name$="-desconto_unitario"], #id_desconto, input[name$="-DELETE"]',
            function () {
                calcularTotais();
            }
        );

        calcularTotais();

        // --- 3. POSICIONAR FIELDSETS FINAIS APÓS OS INLINES (NO FINAL DO FORMULÁRIO) ---
        var $submitRowBottom = $('.submit-row').last();
        var $bottomFieldsets = $('fieldset.venda-fieldset-bottom, .venda-fieldset-bottom').closest('fieldset, details');
        if (!$bottomFieldsets.length) {
            $bottomFieldsets = $('fieldset.venda-fieldset-bottom');
        }
        if ($submitRowBottom.length && $bottomFieldsets.length) {
            $bottomFieldsets.each(function () {
                var $container = $(this).closest('details').length ? $(this).closest('details') : $(this);
                $container.insertBefore($submitRowBottom);
            });
        }

        // --- 4. MODAL E BOTÃO DE FINALIZAÇÃO / FATURAMENTO E IMPRESSÃO DA VENDA ---
        var $printLink = $('.js-print-venda-link').first();
        var $submitRowAll = $('.submit-row');
        if ($printLink.length && $submitRowAll.length && !$('#btn-submit-imprimir-venda').length) {
            var printUrl = $printLink.attr('data-print-url') || $printLink.attr('href');
            var $btnPrintBottom = $(
                '<a href="' + printUrl + '" target="_blank" id="btn-submit-imprimir-venda" ' +
                'style="background:#2563eb; color:#fff; border:none; padding:10px 18px; border-radius:4px; ' +
                'font-weight:700; cursor:pointer; margin-right:8px; font-size:13px; text-decoration:none; display:inline-block;">' +
                '🖨️ Imprimir Venda' +
                '</a>'
            );
            $submitRowAll.prepend($btnPrintBottom);
        }

        var $condField = $('#id_condicao_pagamento');
        if ($condField.length && $('#venda_form').length) {
            var $submitRow = $('.submit-row');
            if ($submitRow.length && !$('#btn-submit-finalizar-venda').length) {
                var $btnSubmitFin = $(
                    '<button type="button" id="btn-submit-finalizar-venda" ' +
                    'style="background:#16a34a; color:#fff; border:none; padding:10px 18px; border-radius:4px; ' +
                    'font-weight:700; cursor:pointer; margin-right:8px; font-size:13px;">' +
                    '✅ Finalizar / Faturar Venda' +
                    '</button>'
                );
                $submitRow.prepend($btnSubmitFin);
            }

            function buildModal() {
                if ($('#venda-fin-modal-backdrop').length) return;

                var condOptions = $('#id_condicao_pagamento').html() || '';
                var contaOptions = $('#id_conta_destino').html() || '<option value="">--- Caixa Geral Padrão ---</option>';

                var modalHtml = '' +
                    '<div id="venda-fin-modal-backdrop" style="display:none; position:fixed; inset:0; background:rgba(15,23,42,0.68); z-index:99999; align-items:center; justify-content:center; padding:16px;">' +
                    '  <div style="background:var(--body-bg, #fff); color:var(--body-fg, #0f172a); width:100%; max-width:820px; border-radius:10px; box-shadow:0 20px 45px rgba(0,0,0,0.35); overflow:hidden; max-height:92vh; display:flex; flex-direction:column;">' +
                    '    <div style="background:#1e293b; color:#fff; padding:16px 22px; display:flex; justify-content:space-between; align-items:center;">' +
                    '      <h3 style="margin:0; font-size:16px; color:#fff;">✅ Finalizar Venda e Gerar Contas a Receber</h3>' +
                    '      <button type="button" id="venda-fin-modal-close" style="background:transparent; border:none; color:#cbd5e1; font-size:22px; cursor:pointer; line-height:1;">&times;</button>' +
                    '    </div>' +
                    '    <div style="padding:20px 22px; overflow-y:auto;">' +
                    '      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; background:var(--darkened-bg, #f8fafc); padding:12px 16px; border-radius:6px; border:1px solid var(--hairline-color, #e2e8f0); margin-bottom:16px;">' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Subtotal dos Itens</span><strong id="m-vnd-subtotal" style="font-size:15px;">R$ 0,00</strong></div>' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Desconto Geral</span><strong id="m-vnd-desc-txt" style="font-size:15px;">R$ 0,00</strong></div>' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Total Líquido a Faturar</span><strong id="m-vnd-total" style="font-size:18px; color:#16a34a;">R$ 0,00</strong></div>' +
                    '      </div>' +
                    '      <div id="m-vnd-alert-cliente" style="display:none; background:#fef2f2; border:1px solid #f87171; color:#991b1b; padding:10px 14px; border-radius:6px; font-size:12px; font-weight:600; margin-bottom:14px;">' +
                    '        ⚠️ Atenção: Para vendas <strong>A Prazo (Em Aberto)</strong> é obrigatório selecionar um Cliente no formulário da venda.' +
                    '      </div>' +
                    '      <div style="margin-bottom:14px;">' +
                    '        <label style="font-weight:700; font-size:13px; display:block; margin-bottom:8px;">1. A Venda já está Quitada / Paga?</label>' +
                    '        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">' +
                    '          <label id="m-vnd-card-pago" style="border:2px solid #cbd5e1; border-radius:8px; padding:12px; cursor:pointer; display:flex; gap:8px; align-items:flex-start;">' +
                    '            <input type="radio" name="m_venda_quitada" value="1" checked style="margin-top:3px;">' +
                    '            <div><strong style="display:block; font-size:13px;">✅ SIM — Quitada (Pago no ato)</strong><span style="font-size:11px; color:#64748b;">Gera o Contas a Receber já baixado como PAGO no Caixa/Conta.</span></div>' +
                    '          </label>' +
                    '          <label id="m-vnd-card-aberto" style="border:2px solid #cbd5e1; border-radius:8px; padding:12px; cursor:pointer; display:flex; gap:8px; align-items:flex-start;">' +
                    '            <input type="radio" name="m_venda_quitada" value="0" style="margin-top:3px;">' +
                    '            <div><strong style="display:block; font-size:13px;">⏳ NÃO — Em Aberto (A Receber)</strong><span style="font-size:11px; color:#64748b;">Gera as parcelas EM ABERTO no Contas a Receber para baixa futura.</span></div>' +
                    '          </label>' +
                    '        </div>' +
                    '      </div>' +
                    '      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin-bottom:14px;">' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Condição de Pagamento</label><select id="m-vnd-condicao" style="width:100%; height:38px !important; min-height:38px !important; line-height:1.4 !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;">' + condOptions + '</select></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Nº de Parcelas</label><input type="number" id="m-vnd-parcelas" min="1" max="120" value="1" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Intervalo entre Parcelas (dias)</label><input type="number" id="m-vnd-intervalo" min="0" max="365" value="30" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">1º Vencimento / Data Pagto</label><input type="date" id="m-vnd-vencimento" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Conta / Caixa de Destino</label><select id="m-vnd-conta" style="width:100%; height:38px !important; min-height:38px !important; line-height:1.4 !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;">' + contaOptions + '</select></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Desconto Geral (R$)</label><input type="number" step="0.01" min="0" id="m-vnd-desconto" value="0.00" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '      </div>' +
                    '      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px;">' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Número NF (Opcional)</label><input type="text" id="m-vnd-nf" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Cupom Fiscal / CF (Opcional)</label><input type="text" id="m-vnd-cf" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '      </div>' +
                    '      <div>' +
                    '        <label style="font-weight:700; font-size:12px; display:block; margin-bottom:6px;">2. Prévia das Parcelas do Contas a Receber</label>' +
                    '        <table style="width:100%; border-collapse:collapse; font-size:12px;">' +
                    '          <thead><tr style="background:var(--darkened-bg, #f1f5f9);"><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Parcela</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Vencimento</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Valor</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Status a Gerar</th></tr></thead>' +
                    '          <tbody id="m-vnd-preview-tbody"></tbody>' +
                    '        </table>' +
                    '      </div>' +
                    '    </div>' +
                    '    <div style="padding:14px 22px; background:var(--darkened-bg, #f8fafc); border-top:1px solid var(--hairline-color, #e2e8f0); display:flex; justify-content:flex-end; gap:10px;">' +
                    '      <button type="button" id="venda-fin-modal-cancel" style="padding:9px 16px; border-radius:5px; border:1px solid #94a3b8; background:transparent; cursor:pointer; font-weight:600; color:var(--body-fg, #334155);">Cancelar</button>' +
                    '      <button type="button" id="venda-fin-modal-confirm" style="padding:9px 20px; border-radius:5px; border:none; background:#16a34a; color:#fff; font-weight:700; cursor:pointer;">✅ Confirmar e Gerar Contas a Receber</button>' +
                    '    </div>' +
                    '  </div>' +
                    '</div>';

                $('body').append(modalHtml);
            }

            function renderModalPreview() {
                var desc = parseNum($('#m-vnd-desconto').val());
                var total = Math.max(0, lastTotals.subtotal - desc);
                $('#m-vnd-subtotal').text('R$ ' + formatMoney(lastTotals.subtotal));
                $('#m-vnd-desc-txt').text('R$ ' + formatMoney(desc));
                $('#m-vnd-total').text('R$ ' + formatMoney(total));

                var quitada = $('input[name="m_venda_quitada"]:checked').val() === '1';
                var temCliente = Boolean($('#id_cliente').val());

                if (quitada) {
                    $('#m-vnd-card-pago').css({ borderColor: '#16a34a', background: 'rgba(22,163,74,0.08)' });
                    $('#m-vnd-card-aberto').css({ borderColor: '#cbd5e1', background: 'transparent' });
                    $('#m-vnd-alert-cliente').hide();
                    $('#venda-fin-modal-confirm').prop('disabled', false).css('opacity', '1');
                } else {
                    $('#m-vnd-card-pago').css({ borderColor: '#cbd5e1', background: 'transparent' });
                    $('#m-vnd-card-aberto').css({ borderColor: '#d97706', background: 'rgba(217,119,6,0.08)' });
                    if (!temCliente) {
                        $('#m-vnd-alert-cliente').show();
                        $('#venda-fin-modal-confirm').prop('disabled', true).css('opacity', '0.5');
                    } else {
                        $('#m-vnd-alert-cliente').hide();
                        $('#venda-fin-modal-confirm').prop('disabled', false).css('opacity', '1');
                    }
                }

                var n = Math.max(1, parseInt($('#m-vnd-parcelas').val() || '1', 10));
                var intervalo = Math.max(0, parseInt($('#m-vnd-intervalo').val() || '30', 10));
                var vencStr = $('#m-vnd-vencimento').val();
                var dtBase = vencStr ? new Date(vencStr + 'T12:00:00') : new Date();

                if (total <= 0) {
                    $('#m-vnd-preview-tbody').html('<tr><td colspan="4" style="padding:8px; text-align:center; color:#64748b;">Venda com valor R$ 0,00 — será finalizada sem gerar títulos.</td></tr>');
                    return;
                }

                var porParcela = Math.round((total / n) * 100) / 100;
                var ultima = Math.round((total - porParcela * (n - 1)) * 100) / 100;
                var rows = '';

                for (var i = 0; i < n; i++) {
                    var val = (i === n - 1) ? ultima : porParcela;
                    var d = new Date(dtBase.getTime());
                    d.setDate(d.getDate() + (intervalo * i));
                    var dd = String(d.getDate()).padStart(2, '0');
                    var mm = String(d.getMonth() + 1).padStart(2, '0');
                    var yyyy = d.getFullYear();

                    var statusHtml = quitada
                        ? '<span style="background:#dcfce7; color:#166534; padding:2px 8px; border-radius:10px; font-weight:700; font-size:11px;">QUITADO (PAGO)</span>'
                        : '<span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:10px; font-weight:700; font-size:11px;">EM ABERTO</span>';

                    rows += '<tr>' +
                        '<td style="padding:6px 10px; border:1px solid #e2e8f0;"><strong>' + (i + 1) + '/' + n + '</strong></td>' +
                        '<td style="padding:6px 10px; border:1px solid #e2e8f0;">' + dd + '/' + mm + '/' + yyyy + '</td>' +
                        '<td style="padding:6px 10px; border:1px solid #e2e8f0;"><strong>R$ ' + formatMoney(val) + '</strong></td>' +
                        '<td style="padding:6px 10px; border:1px solid #e2e8f0;">' + statusHtml + '</td>' +
                        '</tr>';
                }
                $('#m-vnd-preview-tbody').html(rows);
            }

            function openFinalizarModal() {
                calcularTotais();
                buildModal();

                var cond = $('#id_condicao_pagamento').val() || 'DINHEIRO';
                var parc = parseInt($('#id_numero_parcelas').val() || '1', 10) || 1;
                var inter = parseInt($('#id_intervalo_dias').val() || '30', 10);
                if (isNaN(inter)) inter = 30;

                var venc = $('#id_data_primeiro_vencimento').val() || '';
                if (venc && venc.indexOf('/') > -1) {
                    var parts = venc.split('/');
                    if (parts.length === 3) venc = parts[2] + '-' + parts[1] + '-' + parts[0];
                }
                if (!venc) {
                    var now = new Date();
                    venc = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
                }

                $('#m-vnd-condicao').val(cond);
                $('#m-vnd-parcelas').val(parc);
                $('#m-vnd-intervalo').val(inter);
                $('#m-vnd-vencimento').val(venc);
                $('#m-vnd-conta').val($('#id_conta_destino').val() || '');
                $('#m-vnd-desconto').val(lastTotals.desconto.toFixed(2));
                $('#m-vnd-nf').val($('#id_numero_nf').val() || '');
                $('#m-vnd-cf').val($('#id_numero_cupom_fiscal').val() || '');

                var isAvistaPadrao = (cond === 'DINHEIRO' || cond === 'PIX' || cond === 'CARTAO_DEBITO') && parc === 1;
                $('input[name="m_venda_quitada"][value="' + (isAvistaPadrao ? '1' : '0') + '"]').prop('checked', true);

                renderModalPreview();
                $('#venda-fin-modal-backdrop').css('display', 'flex');
            }

            $(document).on('click', '#btn-submit-finalizar-venda, .js-open-finalizar-venda-modal', function (e) {
                e.preventDefault();
                openFinalizarModal();
            });

            $(document).on('click', '#venda-fin-modal-close, #venda-fin-modal-cancel', function () {
                $('#venda-fin-modal-backdrop').hide();
            });

            $(document).on('change', '#m-vnd-condicao', function () {
                var v = $(this).val();
                var n = parseInt($('#m-vnd-parcelas').val() || '1', 10);
                if ((v === 'DINHEIRO' || v === 'PIX' || v === 'CARTAO_DEBITO') && n === 1) {
                    $('input[name="m_venda_quitada"][value="1"]').prop('checked', true);
                } else if (v === 'BOLETO' || v === 'CREDIARIO' || n > 1) {
                    $('input[name="m_venda_quitada"][value="0"]').prop('checked', true);
                }
                renderModalPreview();
            });

            $(document).on('change input', '#m-vnd-parcelas', function () {
                var n = parseInt($(this).val() || '1', 10);
                if (n > 1) {
                    $('input[name="m_venda_quitada"][value="0"]').prop('checked', true);
                }
                renderModalPreview();
            });

            $(document).on('change input', '#m-vnd-intervalo, #m-vnd-vencimento, #m-vnd-desconto, input[name="m_venda_quitada"]', function () {
                renderModalPreview();
            });

            $(document).on('click', '#venda-fin-modal-confirm', function () {
                var quitadaVal = $('input[name="m_venda_quitada"]:checked').val() || '0';
                if (quitadaVal === '0' && !$('#id_cliente').val()) {
                    renderModalPreview();
                    return;
                }

                $('#id_condicao_pagamento').val($('#m-vnd-condicao').val());
                $('#id_numero_parcelas').val($('#m-vnd-parcelas').val());
                $('#id_intervalo_dias').val($('#m-vnd-intervalo').val());
                $('#id_data_primeiro_vencimento').val($('#m-vnd-vencimento').val());
                $('#id_conta_destino').val($('#m-vnd-conta').val());
                $('#id_desconto').val($('#m-vnd-desconto').val());
                $('#id_numero_nf').val($('#m-vnd-nf').val());
                $('#id_numero_cupom_fiscal').val($('#m-vnd-cf').val());

                var $form = $('#venda_form');
                $form.find('input[name="_finalizar_venda"], input[name="_venda_quitada"]').remove();
                $form.append('<input type="hidden" name="_finalizar_venda" value="1">');
                $form.append('<input type="hidden" name="_venda_quitada" value="' + quitadaVal + '">');
                $form.submit();
            });
        }
    }

    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).ready(function () {
            initVendaAdmin(django.jQuery);
        });
    } else if (typeof jQuery !== 'undefined') {
        jQuery(document).ready(function () {
            initVendaAdmin(jQuery);
        });
    }
})();
