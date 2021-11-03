/**
 * Created by david on 10/4/16.
 */

var DatePickerCtrl = function (updateFunction, globalStart, globalEnd) {
    console.log('[DatePickerCtrl] globalStart=' + globalStart);
    console.log('[DatePickerCtrl] globalEnd=' + globalEnd);

    $(document).ready(function () {

        var cb = function (start, end, label) {
            console.log(start.toISOString(), end.toISOString(), label);
            $('#reportrange span').html(start.format('YYYY/MM/DD') + ' - ' + end.format('YYYY/MM/DD'));
        };

        var optionSet1 = {
            minDate: '2015/01/01',
            maxDate: '2025/12/31',
            dateLimit: {
                days: 365
            },
            showDropdowns: true,
            showWeekNumbers: true,
            timePicker: false,
            timePickerIncrement: 1,
            timePicker12Hour: true,
            ranges: {
                'Today': [moment(), moment()],
                'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
                'Last 7 Days': [moment().subtract(6, 'days'), moment()],
                'Last 30 Days': [moment().subtract(29, 'days'), moment()],
                'This Month': [moment().startOf('month'), moment().endOf('month')],
                'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
            },
            opens: 'left',
            buttonClasses: ['btn btn-default'],
            applyClass: 'btn-small btn-primary',
            cancelClass: 'btn-small',
            autoUpdateInput: false,
            format: 'YYYY/MM/DD',
            separator: ' to ',
            locale: {
                applyLabel: 'Submit',
                cancelLabel: 'Last 1K',
                fromLabel: 'From',
                toLabel: 'To',
                customRangeLabel: 'Custom',
                daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
                monthNames: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
                firstDay: 1
            }
        };
        if (globalStart && globalEnd) {
            optionSet1.startDate = moment(globalStart).format('MM/DD/YYYY');
            optionSet1.endDate = moment(globalEnd).format('MM/DD/YYYY');
            $('#reportrange span').html(
                moment(globalStart).format('YYYY/MM/DD') +
                ' - ' +
                moment(globalEnd).format('YYYY/MM/DD')
            );
        } else {
            optionSet1.startDate = moment().format('MM/DD/YYYY');
            optionSet1.endDate = moment().format('MM/DD/YYYY');
        }
        console.log(optionSet1);
        $('#reportrange').daterangepicker(optionSet1, cb);
        $('#reportrange').on('apply.daterangepicker', function (ev, picker) {
            console.log('Apply', picker);
            updateFunction(picker.startDate, picker.endDate);
        });
        $('#reportrange').on('cancel.daterangepicker', function(ev, picker) {
            $(this).val('');
            var newUrl = window.location.pathname;
            console.log('pathname='+ newUrl);
            console.log('goto = ' + newUrl);
            window.location.href = newUrl;

        });
    });
};
