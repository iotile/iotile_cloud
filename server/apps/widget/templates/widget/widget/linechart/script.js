/**
 * Created by david on 6/26/16.
 */

/**
 * In order to synchronize tooltips and crosshairs, override the
 * built-in events with handlers defined on the parent element.
 */


var getFormattedDate = function (d) {
    return moment.utc(d).format('YYYY-MM-DD HH:mm:ss');
};

$('#container').bind('mousemove touchmove touchstart', function (e) {
    var chart,
        point,
        i,
        event;

    var infoPanel = '#info-data';
    $(infoPanel).empty();
    
    for (i = 0; i < Highcharts.charts.length; i = i + 1) {
        chart = Highcharts.charts[i];
        // Find coordinates within the chart
        event = chart.pointer.normalize(e.originalEvent);
        // Get the hovered point
        point = chart.series[0].searchPoint(event, true);
        if (point) {



            if ($(infoPanel).is(':empty')) {
                // console.log(point);

                var listItem = $('<li>', {
                    class: 'list-group-item d-flex justify-content-between lh-condensed'
                });
                var date = getFormattedDate(point.x);
                $('<strong>', {
                    text: date + ' (UTC)',
                 }).appendTo(listItem);
                 $(listItem).appendTo(infoPanel);
            }

            var listItem = $('<li>', {
                class: 'list-group-item d-flex justify-content-between lh-condensed'
            });
            $('<strong>', {
                text: point.series.name,
                css: {color: point.color}, 
             }).appendTo(listItem);

             $('<span>', {
                text: point.y,
                css: {float: "right"}, 
                
             }).appendTo(listItem);

             $(listItem).appendTo(infoPanel);

            point.highlight(e);
        }
    }
});

/**
 * Override the reset function, we don't need to hide the tooltips and
 * crosshairs.
 */
Highcharts.Pointer.prototype.reset = function () {
    return undefined;
};

/**
 * Highlight a point by showing tooltip, setting hover state and draw crosshair
 */
Highcharts.Point.prototype.highlight = function (event) {
    event = this.series.chart.pointer.normalize(event);
    this.onMouseOver(); // Show the hover marker
    this.series.chart.tooltip.refresh(this); // Show the tooltip
    this.series.chart.xAxis[0].drawCrosshair(event, this); // Show the crosshair
};

/**
 * Synchronize zooming through the setExtremes event handler.
 */
function syncExtremes(e) {
    var thisChart = this.chart;

    if (e.trigger !== 'syncExtremes') { // Prevent feedback loop
        Highcharts.each(Highcharts.charts, function (chart) {
            if (chart !== thisChart) {
                if (chart.xAxis[0].setExtremes) { // It is null while updating
                    chart.xAxis[0].setExtremes(
                        e.min,
                        e.max,
                        undefined,
                        false,
                        { trigger: 'syncExtremes' }
                    );
                }
            }
        });
    }
}


var ChartCtrl = function () {

    var chartObjList = [];

    var fetchData = function (url, callback) {
        console.log('Fetching data: ' + url);
        var t0 = Date.now();
        var jsonData = $.ajax({
            url: url,
            dataType: 'json'
        }).done(function (streamData) {
            var t1 = Date.now();
            console.debug('Fetch time: ' + (t1 - t0) + ' with ' + streamData.count + ' elements');
            callback(streamData);
        });
    };

    var addDataPoint = function (chartObj, dataSet, date, value) {
        chartObj.labels.push(date);  // Doo not show anything less than secs
        dataSet.data.push(value);

        // if (StreamUtils.evaluate(parseFloat(value))) {
        //     dataSet.pointBorderColor.push('red');
        //     dataSet.pointBackgroundColor.push('red');
        //     dataSet.pointBorderWidth.push(5);
        //     dataSet.backgroundColor = "#F69292";

        // } else {
        //     dataSet.pointBorderColor.push("rgba(38, 185, 154, 0.7)");
        //     dataSet.pointBackgroundColor.push("rgba(38, 185, 154, 0.7)");
        //     dataSet.pointBorderWidth.push(1);
        //     dataSet.backgroundColor = "rgba(38, 185, 154, 0.31)";
        // }
    };

    var buildEmptyDataSet = function (chartObj) {
        var dataSet = {
            label: chartObj.displayOptions.streamName,
            backgroundColor: [],
            borderColor: "rgba(38, 185, 154, 0.7)",
            pointBorderColor: [],
            pointBackgroundColor: [],
            pointHoverBackgroundColor: "#fff",
            pointHoverBorderColor: "rgba(220,220,220,1)",
            pointBorderWidth: [],
            data: []
        };
        return dataSet;
    };

    var extractChartDataSet = function (dataSet, chartObj, streamData) {
        var lastDate;

        count = 0;
        streamData["results"].forEach(function (packet) {

            lastDate = new Date(packet.timestamp);
            var value = packet.display_value;
            addDataPoint(chartObj, dataSet, lastDate, value);
            count += 1;
        });
        console.log('Processes ', count, 'data points');

        return dataSet;
    };

    var createChartElement = function (chartObj) {

        if (chartObj.datasets && chartObj.labels.length) {

            // build dataset [[x,y], ... ]
            var data = Highcharts.map(chartObj.datasets[0].data, function (val, j) {
                return [chartObj.labels[j].valueOf(), Number(val)];
            });
    
            // Instantiate a new chart
            $('<div class="my-chart">')
            .appendTo('#container')
            .highcharts({
                chart: {
                    height: 220,
                    marginLeft: 50, // Keep all charts left aligned
                    spacingTop: 50,
                    spacingBottom: 20,
                    zoomType: 'x'
                },
                title: {
                    text: chartObj.name,
                    align: 'left',
                    margin: 0,
                    x: 40,
                    style: {
                        fontSize: '15px'
                    }
                },
                credits: {
                    enabled: false
                },
                legend: {
                    enabled: false
                },
                xAxis: {
                    crosshair: true,
                    type: 'datetime',
                    events: {
                        setExtremes: syncExtremes
                    }
                },
                yAxis: {
                    title: {
                        text: null
                    }
                },
                tooltip: {
                    enabled: false
                    
                    // positioner: function () {
                    //     return {
                    //         // right aligned
                    //         x: this.chart.chartWidth - this.label.width,
                    //         y: 10 // align to title
                    //     };
                    // },
                    // borderWidth: 0,
                    // backgroundColor: 'none',
                    // pointFormat: '{point.y}',
                    // headerFormat: '',
                    // shadow: false,
                    // style: {
                    //     fontSize: '18px'
                    // },
                    // valueDecimals: 1
                },
                series: [{
                    data: data,
                    name: chartObj.name,
                    type: 'area',
                    color: Highcharts.getOptions().colors[chartObj.index],
                    fillOpacity: 0.3,
                    tooltip: {
                        valueSuffix: ' ' + chartObj.unit
                    }
                }]
            });

        }
    };

    var initChartDataSets = function (chartObj, withDefaultDates) {

        var initialUrl = chartObj.url;
        if (withDefaultDates) {
            var startDate = moment().subtract(6, 'days');
            initialUrl += "&start=" + startDate.toISOString();
        }
        console.log(initialUrl);
        chartObj.labels = [];
        var dataSet = buildEmptyDataSet(chartObj);
        fetchData(initialUrl, function (streamData) {
            dataSet = extractChartDataSet(dataSet, chartObj, streamData);
            chartObj.datasets = [dataSet];

            chartObj.chart = createChartElement(chartObj);
        });
    };

    var addChartObj = function (chartObj) {
        console.log('[ChartCtrl] addChartObj( ' + chartObj.canvasElementId + ' )');
        chartObjList.push(chartObj);
    };

    var initCharts = function (withDefaultDates) {
        console.log('[ChartCtrl] initCharts()');
        chartObjList.forEach(function (chartObj) {
            console.log('[ChartCtrl] Initializing Chart: ' + chartObj.canvasElementId);
            console.log('[ChartCtrl] -> Using url: ' + chartObj.url);

            initChartDataSets(chartObj, withDefaultDates);
        });
    };

    var updateCharts = function (startDate, endDate) {
        console.log('[ChartCtrl] updateCharts(): start/end dates are ' + startDate.format('MMMM D, YYYY') + " to " + endDate.format('MMMM D, YYYY'));
        console.log('[ChartCtrl] from ' + startDate.toISOString() + " to " + endDate.toISOString());
        chartObjList.forEach(function (chartObj) {
            console.log('[ChartCtrl] Updating Chart1: ' + chartObj.canvasElementId);

            var newUrl = chartObj.url;
            newUrl += "&start=" + startDate.toISOString();
            newUrl += "&end=" + endDate.toISOString();
            console.log(newUrl);

            chartObj.labels = [];

            fetchData(newUrl, function (streamData) {
                var dataSet = extractChartDataSet(streamData, chartObj, startDate, endDate);
                console.log(dataSet);
                console.log('Updating Chart');
                chartObj.chart.config.data.datasets[0] = dataSet;
                chartObj.chart.config.data.labels = chartObj.labels;

                chartObj.chart.update();
            });
        });
    };

    // public api
    return {
        addChartObj: addChartObj,
        initCharts: initCharts,
        updateCharts: updateCharts
    };
};
