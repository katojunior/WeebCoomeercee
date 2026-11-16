(function () {
    'use strict';

    function onlyDigits(value) {
        return (value || '').replace(/\D/g, '');
    }

    function formatCep(value) {
        const digits = onlyDigits(value).slice(0, 8);
        if (digits.length <= 5) {
            return digits;
        }
        return digits.slice(0, 5) + '-' + digits.slice(5);
    }

    function formatPhone(value) {
        const digits = onlyDigits(value).slice(0, 11);
        if (!digits.length) {
            return '';
        }
        if (digits.length <= 2) {
            return '(' + digits;
        }
        if (digits.length <= 6) {
            return '(' + digits.slice(0, 2) + ') ' + digits.slice(2);
        }
        if (digits.length <= 10) {
            return '(' + digits.slice(0, 2) + ') ' + digits.slice(2, 6) + '-' + digits.slice(6);
        }
        return '(' + digits.slice(0, 2) + ') ' + digits.slice(2, 7) + '-' + digits.slice(7);
    }

    function formatCpf(digits) {
        const d = digits.slice(0, 11);
        if (d.length <= 3) {
            return d;
        }
        if (d.length <= 6) {
            return d.slice(0, 3) + '.' + d.slice(3);
        }
        if (d.length <= 9) {
            return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6);
        }
        return d.slice(0, 3) + '.' + d.slice(3, 6) + '.' + d.slice(6, 9) + '-' + d.slice(9);
    }

    function formatCnpj(digits) {
        const d = digits.slice(0, 14);
        if (d.length <= 2) {
            return d;
        }
        if (d.length <= 5) {
            return d.slice(0, 2) + '.' + d.slice(2);
        }
        if (d.length <= 8) {
            return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5);
        }
        if (d.length <= 12) {
            return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5, 8) + '/' + d.slice(8);
        }
        return d.slice(0, 2) + '.' + d.slice(2, 5) + '.' + d.slice(5, 8) + '/' + d.slice(8, 12) + '-' + d.slice(12);
    }

    function formatCpfCnpj(value, tipoPessoaSelect) {
        const digits = onlyDigits(value);
        const tipo = tipoPessoaSelect ? tipoPessoaSelect.value : '';
        if (tipo === '1') {
            return formatCpf(digits);
        }
        if (tipo === '0') {
            return formatCnpj(digits);
        }
        return digits.length <= 11 ? formatCpf(digits) : formatCnpj(digits);
    }

    function bindMask(element, formatter) {
        if (!element) {
            return;
        }
        const apply = function () {
            const formatted = formatter(element.value);
            if (element.value !== formatted) {
                element.value = formatted;
            }
        };
        element.addEventListener('input', apply);
        element.addEventListener('blur', apply);
        apply();
    }

    document.addEventListener('DOMContentLoaded', function () {
        const tipoSelect = document.getElementById('id_juridica_fisica');
        const cpfCnpjInput = document.getElementById('id_cnpj_cpf');

        bindMask(document.getElementById('id_cep'), formatCep);
        bindMask(document.getElementById('id_celular'), formatPhone);
        bindMask(document.getElementById('id_telefone'), formatPhone);
        bindMask(document.getElementById('id_telefone2'), formatPhone);

        if (cpfCnpjInput) {
            bindMask(cpfCnpjInput, function (val) {
                return formatCpfCnpj(val, tipoSelect);
            });
            if (tipoSelect) {
                tipoSelect.addEventListener('change', function () {
                    cpfCnpjInput.value = formatCpfCnpj(cpfCnpjInput.value, tipoSelect);
                });
            }
        }
    });
})();

