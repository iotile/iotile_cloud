/**
 * Created by david on 6/29/16.
 */

var StreamUtils = (function () { // eslint-disable-line no-unused-vars
    'use strict';
    /**
     * Singleton object with utility functions to help with data stream visualization
     *
     * @returns Public Methods
     * @constructor
     */

    var triggers = [];

    var displayYesNo = function (value) {
        if (value) {
            return 'Yes';
        }
        return 'No';
    };

    var checkOneTrigger = function(value, operator, threshold) {
        //console.log(value + ' ' + operator + ' ' + threshold);
        if (operator === 'eq') {
            return (value === threshold);
        }
        if (operator === 'ne') {
            return (value !== threshold);
        }
        if (operator === 'le') {
            return (value <= threshold);
        }
        if (operator === 'lt') {
            return (value < threshold);
        }
        if (operator === 'ge') {
            return (value >= threshold);
        }
        if (operator === 'gt') {
            return (value > threshold);
        }

        return false;
    };

    function resetTriggers() {
        triggers = [];
    }

    function addTrigger(trigger) {
        triggers.push(trigger);
    }

    function checkTriggers(value) {
        var result = false;
        triggers.forEach(function (trigger) {
            if (checkOneTrigger(value, trigger[0], trigger[1])) {
                result = true;
            }
        });
        return result;
    }

    return {
        evaluate: checkTriggers,
        displayYesNo: displayYesNo,
        resetTriggers: resetTriggers,
        addTrigger: addTrigger
    };

})();


