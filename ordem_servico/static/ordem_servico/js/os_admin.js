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

                // Se houver apenas 1 equipamento cadastrado para o cliente e nada selecionado, seleciona-o automaticamente
                if (data && data.equipamentos && data.equipamentos.length === 1 && !foundSelected && !currentVal) {
                    $equip.val(data.equipamentos[0].id);
                }
            });
        }

        // Monitorar mudança no campo cliente (Select2 do Django autocomplete)
        $(document).on('change', '#id_cliente', function () {
            var clienteId = $(this).val();
            carregarEquipamentos(clienteId, null);
        });

        // Se na abertura da página o cliente já estiver preenchido e equipamento sem opções (ou vazio), carrega os equipamentos
        var initialCliente = $('#id_cliente').val();
        var initialEquip = $('#id_equipamento').val();
        if (initialCliente && $('#id_equipamento option').length <= 1) {
            carregarEquipamentos(initialCliente, initialEquip);
        }

        // --- 2. CÁLCULO AUTOMÁTICO DE TOTAIS EM TEMPO REAL ---
        function formatMoney(num) {
            return (num || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function parseNum(val) {
            if (!val) return 0;
            if (typeof val === 'number') return val;
            // Trata formatos brasileiro (1.000,00) e americano (1000.00)
            var clean = String(val).replace(/\s/g, '');
            if (clean.indexOf(',') > -1 && clean.indexOf('.') > -1) {
                clean = clean.replace(/\./g, '').replace(',', '.');
            } else if (clean.indexOf(',') > -1) {
                clean = clean.replace(',', '.');
            }
            return parseFloat(clean) || 0;
        }

        function calcularTotais() {
            var totalPecas = 0;
            var totalServicos = 0;

            // Percorre as linhas da tabela inline de itens/peças/serviços
            $('tr.form-row, .tabular.inline-related tbody tr').each(function () {
                var $row = $(this);
                if ($row.hasClass('empty-form')) return;

                // Linhas marcadas para exclusão não entram no cálculo
                var isDeleted = $row.find('.field-DELETE input:checked, input[name$="-DELETE"]:checked').length > 0;
                if (isDeleted) return;

                var tipo = $row.find('[name$="-tipo_item"]').val();
                var qtd = parseNum($row.find('[name$="-quantidade"]').val());
                var unit = parseNum($row.find('[name$="-valor_unitario"]').val());
                var rowTotal = qtd * unit;

                // Atualiza o display do valor_total na linha (campo readonly)
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

            var desc = parseNum($('#id_desconto').val());
            var totalGeral = Math.max(0, (totalPecas + totalServicos) - desc);

            // Atualiza os displays do fieldset de Valores e Faturamento
            $('.field-valor_pecas .readonly, .field-valor_pecas p').text(formatMoney(totalPecas));
            $('.field-valor_servicos .readonly, .field-valor_servicos p').text(formatMoney(totalServicos));
            $('.field-valor_total .readonly, .field-valor_total p').text(formatMoney(totalGeral));
        }

        // Dispara o cálculo em qualquer digitação ou mudança nos campos relevantes
        $(document).on(
            'input change keyup',
            '[name$="-quantidade"], [name$="-valor_unitario"], [name$="-tipo_item"], #id_desconto, input[name$="-DELETE"]',
            function () {
                calcularTotais();
            }
        );

        // Executa cálculo inicial ao abrir o formulário
        calcularTotais();
    }

    // Inicializa com django.jQuery
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
