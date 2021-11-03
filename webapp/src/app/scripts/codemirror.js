/* Any changes to this file require /server/apps/utils/codemirror/widget.py to be
 * updated with the Gulp generated codemirror-XXXXXXXXXXX.js file name
 */

(function(){
    CodeMirror.defineSimpleMode("sgf", {
  // The start state contains the rules that are intially used
  start: [
    // The regex matches the token, the token property contains the type
    {regex: /"(?:[^\\]|\\.)*?(?:"|$)/, token: "string"},
    // You can match multiple tokens at once. Note that the captured
    // groups must span the whole string in this case
    {regex: /(function)(\s+)([a-z$][\w$]*)/,
     token: ["keyword", null, "variable-2"]},
    // Rules are matched in the order in which they appear, so there is
    // no ambiguity between this one and the one above
    {regex: /(?:on|when|every|config|manual|realtime|copy|set)\b/,
     token: "keyword"},
    {regex: /connect|connected|streamer|unbuffered|input|output|uint32_t/, token: "atom"},
    {regex: /0x[a-f\d]+|[-+]?(?:\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/i,
     token: "number"},
    {regex: /#.*/, token: "comment"},
    {regex: /[-+\/*=<>!]+/, token: "operator"},
    // indent and dedent properties guide autoindentation
    {regex: /\{\(/, indent: true},
    {regex: /\}\)/, dedent: true},
    // You can embed other modes with the mode property. This rule
    // causes all code between << and >> to be highlighted with the XML
    // mode.
    {regex: /<</, token: "meta", mode: {spec: "xml", end: />>/}}
  ],
  // The meta property contains global information about the mode. It
  // can contain properties like lineComment, which are supported by
  // all modes, and also directives like dontIndentStates, which are
  // specific to simple modes.
  meta: {
    dontIndentStates: ["comment"],
    lineComment: "//"
  }
});
    var $ = jQuery;
    $(document).ready(function(){
        $('textarea.json-editor').each(function(idx, el){
            CodeMirror.fromTextArea(el, {
                lineNumbers: true,
                lineWrapping: true,
                mode: 'javascript'
            });
        });
        $('textarea.sgf-editor').each(function(idx, el){
            CodeMirror.fromTextArea(el, {
                lineNumbers: true,
                lineWrapping: true,
                mode: 'sgf'
            });
        });
    });
})();
