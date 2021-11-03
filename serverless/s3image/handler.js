'use strict';
// Based on http://jice.lavocat.name/blog/2015/image-conversion-using-amazon-lambda-and-s3-in-node.js/

// dependencies
var async = require('async');
var path = require('path');
var AWS = require('aws-sdk');
var gm = require('gm').subClass({ imageMagick: true });
var util = require('util');
var s3 = new AWS.S3();

exports.resize = function(event, context, cb) {
    // Get Stage from function name
    var t0 = Date.now();
    var functionName = context.functionName;
    var stage = functionName.split('-')[1];

    // Read options from the event.
    //console.log("Reading options from event:\n", util.inspect(event, {depth: 5}));
    var srcBucket = event.Records[0].s3.bucket.name;
    var srcKey = event.Records[0].s3.object.key;
    var dstKey = 'error';

    // Assuming srcKey is of the format dev/incoming/ce21d3cb-e56f-4015-9a0b-58292037ec15/original.jpg
    // 1.- Get srcPath: dev/incoming/ce21d3cb-e56f-4015-9a0b-58292037ec15
    var srcPath = path.dirname(srcKey);
    // 2.- Get UUID: ce21d3cb-e56f-4015-9a0b-58292037ec15
    var imageUuid = path.basename(srcPath);
    // 3.- Get dstPath
    var dstPath = srcPath.replace('incoming', 'images');

    var _400px = {
        width: 400,
        height: 400,
        dstnKey: srcKey,
        destinationPath: 'medium'
    };
    var _100px = {
        width: 100,
        height: 100,
        dstnKey: srcKey,
        destinationPath: 'thumbnail'
    };
    var _28px = {
        width: 28,
        height: 28,
        dstnKey: srcKey,
        destinationPath: 'tiny'
    };
    var _sizesArray = [_100px, _400px, _28px];
    var results = [];
    var cachedResponze;

    function myLog(msg) {

        console.log(msg);
        results.push(msg);
    }

    // Transform, and upload to same S3 bucket but to a different S3 bucket.
    async.forEachOfLimit(_sizesArray, 1, function(value, key, callback) {
        async.waterfall([

            function download(next) {
                if (!cachedResponze) {
                    console.time('downloadImage');

                    // Download the image from S3 into a buffer.
                    // sadly it downloads the image several times, but we couldn't place it outside
                    // the variable was not recognized
                    myLog('Downloading ' + srcBucket + ':' + srcKey);
                    s3.getObject({
                        Bucket: srcBucket,
                        Key: srcKey
                    }, next);
                    console.timeEnd('downloadImage');
                } else {
                    myLog('Reusing ' + srcBucket + ':' + srcKey);
                    next(null, cachedResponze);
                }
            },
            function cache(response, next) {
                if (!cachedResponze) {
                    cachedResponze = response;
                }
                next(null, cachedResponze.Body);
            },
            function process(response, next) {
                console.log('process image');
                // Transform the image buffer in memory.
                gm(response).size(function(err, size) {
                    // Infer the scaling factor to avoid stretching the image unnaturally.
                    if (err) {
                        myLog(err);
                        next(err);
                    }
                    var width = _sizesArray[key].width;
                    var height = _sizesArray[key].height;
                    myLog('resize ' + key + ' width : ' + width + ', height :' + height);

                    console.time('ImgResize');
                    var index = key;
                    //this.resize({width: width, height: height, format: 'jpg',})
                    this.resize(width, height, '^').gravity('Center').crop(width, height).toBuffer(
                        'JPG', function(err, buffer) {
                            console.timeEnd('ImgResize');
                            if (err) {
                                next(err);
                            } else {
                                next(null, buffer, key);
                            }
                        });
                });
            },
            function upload(data, index, next) {
                console.time('uploadImage');
                var dstKey = dstPath + '/' + _sizesArray[index].destinationPath + '.jpg';
                // For the next download, use the smaller picture size
                srcKey = dstKey;
                myLog('upload ' + index + ' to path: ' + dstKey);
                // Stream the transformed image to a different folder.
                s3.putObject({
                    Bucket: srcBucket,
                    Key: dstKey,
                    Body: data,
                    ContentType: 'JPG'
                }, next);
            }
        ], function(err, result) {
            if (err) {
                myLog(err);
            } else {
                console.timeEnd('uploadImage');
            }
            // result now equals 'done'
            var t1 = Date.now();
            myLog('End of step ' + key + '. Exec time: ' + (t1 - t0));
            callback();
        });
    }, function(err) {
        if (err) {
            console.error(
                'Unable to resize ' + srcBucket + '/' + srcKey +
                ' and upload to ' + srcBucket + '/' + dstKey +
                ' due to an error: ' + err
            );
        } else {
            console.log(
                'Successfully resized ' + srcBucket + '/' + srcKey +
                ' and uploaded to ' + srcBucket + '/' + dstKey
            );
        }

        var t1 = Date.now();
        myLog('Total Exec time: ' + (t1 - t0));
      cb(null, {
          message: 'Go Serverless v1.0! Your function executed successfully!',
          srcBucket: srcBucket,
          srcKey: srcKey,
          srcPath: srcPath,
          err: err,
          log: results
      });
    });
};