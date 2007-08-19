// To support tagging on Omidyar.net
// this lets people tag in-place.  It reacts to the submit button
// on a My Tags: text box.  It calls ./tags on the server, which 
// applies the tags, and returns the json for the resulting tag list
// 
// It also lets people click on tags to move them to their edit box
// 
appendToTextInput = function(text, input_id) {
    elt = MochiKit.DOM.getElement(input_id);
    // look for the text surrounded by word boundaries
    pattern = new RegExp ("\\b" + text + "\\b");
    if (pattern.exec(elt.value) == null) {
        elt.value = elt.value + " " + text;
    }
}

// Asyncronous tagging
onPageLoad = function() {
    // attach our form handler to any tagging forms
    var elems = MochiKit.DOM.getElementsByTagAndClassName("form", "tag_form");
    for (var i = 0; i < elems.length; i++) {
        var elem = elems[i];
        // on submit, call our onTagFormSubmit
        MochiKit.Signal.connect(elem, 'onsubmit', onTagFormSubmit);
    }

    elems = MochiKit.DOM.getElementsByTagAndClassName("input", "tag_input");
    for (i = 0; i < elems.length; i++) {
        var elem = elems[i];
        MochiKit.Signal.connect(elem, "onfocus", onTagFocus);
    }
}
MochiKit.Signal.connect(window, "onload", onPageLoad);

onTagFocus = function(event) {
    tools_area_id = this.attributes["tools_id"].value;
    MochiKit.DOM.removeElementClass(tools_area_id, "hidden");
    return true;
}

tagThis = function (oid) {
    MochiKit.DOM.addElementClass("tag_this_"+oid, "hidden");
    MochiKit.DOM.removeElementClass("tag_form_"+oid, "hidden");
    MochiKit.DOM.removeElementClass("tag_current_"+oid, "hidden");
    MochiKit.DOM.getElement("tag_text_"+oid).focus();
}

onTagFormSubmit = function(event) {
    event.stopPropagation();
    event.preventDefault();

    var tags = this.tags.value;
    log ("got tags: " + tags);

    var params = { 
        "format":"json",
        "item_oid":this.item_oid.value,
        "tags":tags
    };

    // Submit the form, and set up success and fail handlers
    var request = loadJSONDoc(this.action, params);
    request.addCallbacks(onTagFormSuccess, onTagFormFailure);

    tools_id = "tag_current_" + this.item_oid.value;
    message = "Updating tags... please wait. ";
    MochiKit.DOM.removeElementClass(tools_id, "hidden");
    getElement(tools_id).innerHTML=message;

    // no default action
    return false;
}

onTagFormSuccess = function(result) {
    // Update the current tags field associated with the 
    // particular form
    //
    text_area_id = "tag_text_" + result.item_oid;
    getElement(text_area_id).value = result.newtags;

    // 
    tools_id = "tag_current_" + result.item_oid;
    message = "Your tags have been applied.";
    getElement(tools_id).innerHTML=message;

    MochiKit.Visual.Highlight(tools_id)
    //MochiKit.DOM.swapDOM(tools_id, message);
    //alert ("tagged!");
}

onTagFormFailure = function(result) {
    // Warn that it failed, with 'please try again soon'
    alert ("Your tagging request failed.  Please let us know.");
}


