(function () {
    'use strict';

    function initOSAdmin($) {
        // --- 1. CARREGAMENTO DINÂMICO DE EQUIPAMENTOS POR CLIENTE ---
        function carregarEquipamentos(clienteId, selectedId) {
            var $equip = $('#id_equipamento');
            if (!$equip.length) return;

            if (!clienteId) {
                $equip.html('<option value="">---------</option>');
                return;
            }

            var url = '/admin/ordem_servico/ordemservico/equipamentos-cliente/' + clienteId + '/';
            $.getJSON(url, function (data) {
                var currentVal = selectedId || $equip.val();
                var options = '<option value="">---------</option>';
                var foundSelected = false;

                if (data && data.equipamentos) {
                    $.each(data.equipamentos, function (idx, item) {
                        var isSel = (currentVal && String(currentVal) === String(item.id)) ? ' selected' : '';
                        if (isSel) foundSelected = true;
                        options += '<option value="' + item.id + '"' + isSel + '>' + item.descricao + '</option>';
                    });
                }
                $equip.html(options);

                if (data && data.equipamentos && data.equipamentos.length === 1 && !foundSelected && !currentVal) {
                    $equip.val(data.equipamentos[0].id);
                }
            });
        }

        $(document).on('change', '#id_cliente', function () {
            var clienteId = $(this).val();
            carregarEquipamentos(clienteId, null);
        });

        var initialCliente = $('#id_cliente').val();
        var initialEquip = $('#id_equipamento').val();
        if (initialCliente && $('#id_equipamento option').length <= 1) {
            carregarEquipamentos(initialCliente, initialEquip);
        }

        // --- 1.5. AUTO-PREENCHIMENTO DO VALOR UNITÁRIO AO SELECIONAR PRODUTO (MANTENDO EDITÁVEL) ---
        $(document).on('change', 'select[name$="-produto"]', function () {
            var $select = $(this);
            var prodId = $select.val();
            if (!prodId) return;

            var $row = $select.closest('tr.form-row, .inline-related');
            var $unitInput = $row.find('input[name$="-valor_unitario"]');
            if (!$unitInput.length) return;

            var url = '/admin/ordem_servico/ordemservico/preco-produto/' + prodId + '/';
            $.getJSON(url, function (data) {
                if (data && data.preco_venda !== undefined) {
                    $unitInput.val(Number(data.preco_venda).toFixed(2));
                    calcularTotais();
                }
            });
        });

        // --- 2. CÁLCULO AUTOMÁTICO DE TOTAIS EM TEMPO REAL ---
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

        var lastTotals = { pecas: 0, servicos: 0, desconto: 0, total: 0 };

        function calcularTotais() {
            var totalPecas = 0;
            var totalServicos = 0;

            $('tr.form-row, .tabular.inline-related tbody tr').each(function () {
                var $row = $(this);
                if ($row.hasClass('empty-form')) return;

                var isDeleted = $row.find('.field-DELETE input:checked, input[name$="-DELETE"]:checked').length > 0;
                if (isDeleted) return;

                var $tipoEl = $row.find('[name$="-tipo_item"]');
                if (!$tipoEl.length) return;

                var tipo = $tipoEl.val();
                var qtd = parseNum($row.find('[name$="-quantidade"]').val());
                var unit = parseNum($row.find('[name$="-valor_unitario"]').val());
                var rowTotal = qtd * unit;

                var $rowTotalDisplay = $row.find('.field-valor_total .readonly, .field-valor_total p');
                if ($rowTotalDisplay.length) {
                    $rowTotalDisplay.text(formatMoney(rowTotal));
                }

                if (tipo === 'PECA') {
                    totalPecas += rowTotal;
                } else if (tipo === 'SERVICO') {
                    totalServicos += rowTotal;
                }
            });

            // Se a OS já estiver bloqueada (sem inputs editáveis nas linhas), lê dos campos readonly
            if (!$('[name$="-tipo_item"]').length) {
                totalPecas = parseNum($('.field-valor_pecas .readonly, .field-valor_pecas p').first().text());
                totalServicos = parseNum($('.field-valor_servicos .readonly, .field-valor_servicos p').first().text());
            }

            var desc = $('#id_desconto').length
                ? parseNum($('#id_desconto').val())
                : parseNum($('.field-desconto .readonly, .field-desconto p').first().text());
            var totalGeral = Math.max(0, (totalPecas + totalServicos) - desc);

            lastTotals = { pecas: totalPecas, servicos: totalServicos, desconto: desc, total: totalGeral };

            $('.field-valor_pecas .readonly, .field-valor_pecas p').text(formatMoney(totalPecas));
            $('.field-valor_servicos .readonly, .field-valor_servicos p').text(formatMoney(totalServicos));
            $('.field-valor_total .readonly, .field-valor_total p').text(formatMoney(totalGeral));
        }

        $(document).on(
            'input change keyup',
            '[name$="-quantidade"], [name$="-valor_unitario"], [name$="-tipo_item"], #id_desconto, input[name$="-DELETE"]',
            function () {
                calcularTotais();
            }
        );

        calcularTotais();

        // --- 2.5. POSICIONAR FIELDSETS FINAIS APÓS OS INLINES (NO FINAL DO FORMULÁRIO) ---
        var $submitRowBottom = $('.submit-row').last();
        var $bottomFieldsets = $('fieldset.os-fieldset-bottom, .os-fieldset-bottom').closest('fieldset, details');
        if (!$bottomFieldsets.length) {
            $bottomFieldsets = $('fieldset.os-fieldset-bottom');
        }
        if ($submitRowBottom.length && $bottomFieldsets.length) {
            $bottomFieldsets.each(function () {
                // Em Django 5+/6+, fieldsets colapsáveis podem estar envolvidos em <details>
                var $container = $(this).closest('details').length ? $(this).closest('details') : $(this);
                $container.insertBefore($submitRowBottom);
            });
        }

        // --- 3. MODAL E BOTÃO DE FINALIZAÇÃO / FATURAMENTO E IMPRESSÃO DA OS ---
        var $printLink = $('.js-print-os-link').first();
        var $submitRowAll = $('.submit-row');
        if ($printLink.length && $submitRowAll.length && !$('#btn-submit-imprimir-os').length) {
            var printUrl = $printLink.attr('data-print-url') || $printLink.attr('href');
            var $btnPrintBottom = $(
                '<a href="' + printUrl + '" target="_blank" id="btn-submit-imprimir-os" ' +
                'style="background:#2563eb; color:#fff; border:none; padding:10px 18px; border-radius:4px; ' +
                'font-weight:700; cursor:pointer; margin-right:8px; font-size:13px; text-decoration:none; display:inline-block;">' +
                '🖨️ Imprimir OS' +
                '</a>'
            );
            $submitRowAll.prepend($btnPrintBottom);
        }

        var $condField = $('#id_condicao_pagamento');
        // Se o campo condicao_pagamento é editável, a OS está em aberto (não finalizada)
        if ($condField.length && $('#ordemservico_form').length) {
            var $submitRow = $('.submit-row');
            if ($submitRow.length && !$('#btn-submit-finalizar-os').length) {
                var $btnSubmitFin = $(
                    '<button type="button" id="btn-submit-finalizar-os" ' +
                    'style="background:#16a34a; color:#fff; border:none; padding:10px 18px; border-radius:4px; ' +
                    'font-weight:700; cursor:pointer; margin-right:8px; font-size:13px;">' +
                    '✅ Finalizar / Faturar OS' +
                    '</button>'
                );
                $submitRow.prepend($btnSubmitFin);
            }

            function buildModal() {
                if ($('#os-fin-modal-backdrop').length) return;

                var condOptions = $('#id_condicao_pagamento').html() || '';
                var contaOptions = $('#id_conta_destino').html() || '<option value="">--- Caixa Geral Padrão ---</option>';

                var modalHtml = '' +
                    '<div id="os-fin-modal-backdrop" style="display:none; position:fixed; inset:0; background:rgba(15,23,42,0.68); z-index:99999; align-items:center; justify-content:center; padding:16px;">' +
                    '  <div style="background:var(--body-bg, #fff); color:var(--body-fg, #0f172a); width:100%; max-width:820px; border-radius:10px; box-shadow:0 20px 45px rgba(0,0,0,0.35); overflow:hidden; max-height:92vh; display:flex; flex-direction:column;">' +
                    '    <div style="background:#1e293b; color:#fff; padding:16px 22px; display:flex; justify-content:space-between; align-items:center;">' +
                    '      <h3 style="margin:0; font-size:16px; color:#fff;">✅ Finalizar Ordem de Serviço e Gerar Contas a Receber</h3>' +
                    '      <button type="button" id="os-fin-modal-close" style="background:transparent; border:none; color:#cbd5e1; font-size:22px; cursor:pointer; line-height:1;">&times;</button>' +
                    '    </div>' +
                    '    <div style="padding:20px 22px; overflow-y:auto;">' +
                    '      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; background:var(--darkened-bg, #f8fafc); padding:12px 16px; border-radius:6px; border:1px solid var(--hairline-color, #e2e8f0); margin-bottom:16px;">' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Total Peças</span><strong id="m-os-pecas" style="font-size:15px;">R$ 0,00</strong></div>' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Total Serviços</span><strong id="m-os-servicos" style="font-size:15px;">R$ 0,00</strong></div>' +
                    '        <div><span style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:600; display:block;">Total Líquido a Faturar</span><strong id="m-os-total" style="font-size:18px; color:#16a34a;">R$ 0,00</strong></div>' +
                    '      </div>' +
                    '      <div style="margin-bottom:14px;">' +
                    '        <label style="font-weight:700; font-size:13px; display:block; margin-bottom:8px;">1. A Ordem de Serviço já está Quitada / Paga?</label>' +
                    '        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">' +
                    '          <label id="m-card-pago" style="border:2px solid #cbd5e1; border-radius:8px; padding:12px; cursor:pointer; display:flex; gap:8px; align-items:flex-start;">' +
                    '            <input type="radio" name="m_os_quitada" value="1" checked style="margin-top:3px;">' +
                    '            <div><strong style="display:block; font-size:13px;">✅ SIM — Quitada (Pago no ato)</strong><span style="font-size:11px; color:#64748b;">Gera o Contas a Receber já baixado como PAGO no Caixa/Conta.</span></div>' +
                    '          </label>' +
                    '          <label id="m-card-aberto" style="border:2px solid #cbd5e1; border-radius:8px; padding:12px; cursor:pointer; display:flex; gap:8px; align-items:flex-start;">' +
                    '            <input type="radio" name="m_os_quitada" value="0" style="margin-top:3px;">' +
                    '            <div><strong style="display:block; font-size:13px;">⏳ NÃO — Em Aberto (A Receber)</strong><span style="font-size:11px; color:#64748b;">Gera as parcelas EM ABERTO no Contas a Receber para baixa futura.</span></div>' +
                    '          </label>' +
                    '        </div>' +
                    '      </div>' +
                    '      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin-bottom:14px;">' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Condição de Pagamento</label><select id="m-os-condicao" style="width:100%; height:38px !important; min-height:38px !important; line-height:1.4 !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;">' + condOptions + '</select></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Nº de Parcelas</label><input type="number" id="m-os-parcelas" min="1" max="120" value="1" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Intervalo entre Parcelas (dias)</label><input type="number" id="m-os-intervalo" min="0" max="365" value="30" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">1º Vencimento / Data Pagto</label><input type="date" id="m-os-vencimento" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Conta / Caixa de Destino</label><select id="m-os-conta" style="width:100%; height:38px !important; min-height:38px !important; line-height:1.4 !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;">' + contaOptions + '</select></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Desconto (R$)</label><input type="number" step="0.01" min="0" id="m-os-desconto" value="0.00" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '      </div>' +
                    '      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px;">' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Número NF (Opcional)</label><input type="text" id="m-os-nf" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '        <div><label style="font-weight:600; font-size:12px; display:block; margin-bottom:4px;">Cupom Fiscal / CF (Opcional)</label><input type="text" id="m-os-cf" style="width:100%; height:38px !important; min-height:38px !important; padding:6px 10px !important; border-radius:4px; border:1px solid #cbd5e1; box-sizing:border-box;"></div>' +
                    '      </div>' +
                    '      <div>' +
                    '        <label style="font-weight:700; font-size:12px; display:block; margin-bottom:6px;">2. Prévia das Parcelas do Contas a Receber</label>' +
                    '        <table style="width:100%; border-collapse:collapse; font-size:12px;">' +
                    '          <thead><tr style="background:var(--darkened-bg, #f1f5f9);"><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Parcela</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Vencimento</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Valor</th><th style="padding:6px 10px; border:1px solid #e2e8f0; text-align:left;">Status a Gerar</th></tr></thead>' +
                    '          <tbody id="m-os-preview-tbody"></tbody>' +
                    '        </table>' +
                    '      </div>' +
                    '    </div>' +
                    '    <div style="padding:14px 22px; background:var(--darkened-bg, #f8fafc); border-top:1px solid var(--hairline-color, #e2e8f0); display:flex; justify-content:flex-end; gap:10px;">' +
                    '      <button type="button" id="os-fin-modal-cancel" style="padding:9px 16px; border-radius:5px; border:1px solid #94a3b8; background:transparent; cursor:pointer; font-weight:600; color:var(--body-fg, #334155);">Cancelar</button>' +
                    '      <button type="button" id="os-fin-modal-confirm" style="padding:9px 20px; border-radius:5px; border:none; background:#16a34a; color:#fff; font-weight:700; cursor:pointer;">✅ Confirmar e Gerar Contas a Receber</button>' +
                    '    </div>' +
                    '  </div>' +
                    '</div>';

                $('body').append(modalHtml);
            }

            function renderModalPreview() {
                var desc = parseNum($('#m-os-desconto').val());
                var total = Math.max(0, (lastTotals.pecas + lastTotals.servicos) - desc);
                $('#m-os-pecas').text('R$ ' + formatMoney(lastTotals.pecas));
                $('#m-os-servicos').text('R$ ' + formatMoney(lastTotals.servicos));
                $('#m-os-total').text('R$ ' + formatMoney(total));

                var quitada = $('input[name="m_os_quitada"]:checked').val() === '1';
                if (quitada) {
                    $('#m-card-pago').css({ borderColor: '#16a34a', background: 'rgba(22,163,74,0.08)' });
                    $('#m-card-aberto').css({ borderColor: '#cbd5e1', background: 'transparent' });
                } else {
                    $('#m-card-pago').css({ borderColor: '#cbd5e1', background: 'transparent' });
                    $('#m-card-aberto').css({ borderColor: '#d97706', background: 'rgba(217,119,6,0.08)' });
                }

                var n = Math.max(1, parseInt($('#m-os-parcelas').val() || '1', 10));
                var intervalo = Math.max(0, parseInt($('#m-os-intervalo').val() || '30', 10));
                var vencStr = $('#m-os-vencimento').val();
                var dtBase = vencStr ? new Date(vencStr + 'T12:00:00') : new Date();

                if (total <= 0) {
                    $('#m-os-preview-tbody').html('<tr><td colspan="4" style="padding:8px; text-align:center; color:#64748b;">OS com valor R$ 0,00 — será finalizada sem gerar títulos.</td></tr>');
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
                $('#m-os-preview-tbody').html(rows);
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

                $('#m-os-condicao').val(cond);
                $('#m-os-parcelas').val(parc);
                $('#m-os-intervalo').val(inter);
                $('#m-os-vencimento').val(venc);
                $('#m-os-conta').val($('#id_conta_destino').val() || '');
                $('#m-os-desconto').val(lastTotals.desconto.toFixed(2));
                $('#m-os-nf').val($('#id_numero_nf').val() || '');
                $('#m-os-cf').val($('#id_numero_cupom_fiscal').val() || '');

                var isAvistaPadrao = (cond === 'DINHEIRO' || cond === 'PIX' || cond === 'CARTAO_DEBITO') && parc === 1;
                $('input[name="m_os_quitada"][value="' + (isAvistaPadrao ? '1' : '0') + '"]').prop('checked', true);

                renderModalPreview();
                $('#os-fin-modal-backdrop').css('display', 'flex');
            }

            $(document).on('click', '#btn-submit-finalizar-os, .js-open-finalizar-os-modal', function (e) {
                e.preventDefault();
                openFinalizarModal();
            });

            $(document).on('click', '#os-fin-modal-close, #os-fin-modal-cancel', function () {
                $('#os-fin-modal-backdrop').hide();
            });

            $(document).on('change', '#m-os-condicao', function () {
                var v = $(this).val();
                var n = parseInt($('#m-os-parcelas').val() || '1', 10);
                if ((v === 'DINHEIRO' || v === 'PIX' || v === 'CARTAO_DEBITO') && n === 1) {
                    $('input[name="m_os_quitada"][value="1"]').prop('checked', true);
                } else if (v === 'BOLETO' || v === 'CREDIARIO' || n > 1) {
                    $('input[name="m_os_quitada"][value="0"]').prop('checked', true);
                }
                renderModalPreview();
            });

            $(document).on('change input', '#m-os-parcelas', function () {
                var n = parseInt($(this).val() || '1', 10);
                if (n > 1) {
                    $('input[name="m_os_quitada"][value="0"]').prop('checked', true);
                }
                renderModalPreview();
            });

            $(document).on('change input', '#m-os-intervalo, #m-os-vencimento, #m-os-desconto, input[name="m_os_quitada"]', function () {
                renderModalPreview();
            });

            $(document).on('click', '#os-fin-modal-confirm', function () {
                $('#id_condicao_pagamento').val($('#m-os-condicao').val());
                $('#id_numero_parcelas').val($('#m-os-parcelas').val());
                $('#id_intervalo_dias').val($('#m-os-intervalo').val());
                $('#id_data_primeiro_vencimento').val($('#m-os-vencimento').val());
                $('#id_conta_destino').val($('#m-os-conta').val());
                $('#id_desconto').val($('#m-os-desconto').val());
                $('#id_numero_nf').val($('#m-os-nf').val());
                $('#id_numero_cupom_fiscal').val($('#m-os-cf').val());

                var $form = $('#ordemservico_form');
                $form.find('input[name="_finalizar_os"], input[name="_os_quitada"]').remove();
                var quitadaVal = $('input[name="m_os_quitada"]:checked').val() || '0';
                $form.append('<input type="hidden" name="_finalizar_os" value="1">');
                $form.append('<input type="hidden" name="_os_quitada" value="' + quitadaVal + '">');
                $form.submit();
            });
        }
    }

    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).ready(function () {
            initOSAdmin(django.jQuery);
        });
    } else if (typeof jQuery !== 'undefined') {
        jQuery(document).ready(function () {
            initOSAdmin(jQuery);
        });
    }
})();
