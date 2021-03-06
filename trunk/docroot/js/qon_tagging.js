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
    
    showControlMenu();

//    var commentEntry = MochiKit.DOM.getElementsByTagAndClassName("textarea")[0];
//    if (null == commentEntry) {
//        return;
//    }
//    MochiKit.Signal.connect(commentEntry, "onkeypress", checkShortcuts);
}
MochiKit.Signal.connect(window, "onload", onPageLoad);

controlCell = function() {
    var commentEntry = MochiKit.DOM.getElementsByTagAndClassName("textarea")[0];
    if (null == commentEntry) {
        return null;
    }
    //MochiKit.DOM.insertSiblingNodesAfter(commentEntry, helpers); // if span above
    var nextCell = commentEntry.parentNode.nextSibling;
    //var nextCell = commentEntry.parentElement.nextElementSibling;
    return nextCell;
}

showControlMenu = function() {
    var cs = controlCell();
    if (null == cs) {
        return;
    }
    var d = MochiKit.DOM;
    var helpers = d.TD({id:"comment_help"}, 
      d.A({'onclick':'showInsertLink()', 'href':'javascript:void(0);'}, 'Insert link'), d.BR()
      );//d.A({'onclick':'showInsertImage()', 'href':'javascript:void(0);'}, 'Upload image and insert link'));
    MochiKit.DOM.swapDOM(cs, helpers);
}

checkShortcuts = function(event)
{
    var code = event.key().code;
    var mods = event.modifier();

    if (code == 76 && (mods.meta || mods.ctrl)) 
    {
        event.preventDefault();
        showInsertLink(null);
    }
}

preventDefaultInsertLink = function(event)
{
    if (event.key().code == 13) {
        event.preventDefault();
        insertLink(null);
    }
}

showInsertLink = function(event) {
    var cs = controlCell();
    if (null == cs) {
        return;
    }
    var d = MochiKit.DOM;
    var ta = MochiKit.DOM.getElementsByTagAndClassName("textarea")[0];
    var selected = '';
    if (ta.selectionBegin != ta.selectionEnd)
    {
        selected = ta.value.slice(ta.selectionBegin, ta.selectionEnd);
    }
    
    var helpers = d.TD({id:"link_inserter"}, 
      d.TABLE(null, 
          TR(null, TD(null, "Show:"), TD(null, d.INPUT({'type':'text', 'id':'new_showas', 'name': 'show_as'})) ),
          TR(null, TD(null, "Link:"), TD(null, d.INPUT({'type':'text', 'id':'new_link', 'name': 'link'})) )
      ),
      d.A({'onclick':'showControlMenu()', 'href':'javascript:void(0);'}, 'Cancel'), " | ",
      d.A({'onclick':'insertLink()', 'href':'javascript:void(0);'}, 'Insert Link') 
      );
    MochiKit.DOM.swapDOM(cs, helpers);
    var link = MochiKit.DOM.getElement("new_link");
    var showas = MochiKit.DOM.getElement("new_showas");
    MochiKit.Signal.connect(link, 'onkeypress', preventDefaultInsertLink);
    MochiKit.Signal.connect(showas, 'onkeypress', preventDefaultInsertLink);
}

insertLink = function(event) {
    var link = MochiKit.DOM.getElement("new_link").value;
    var showas = MochiKit.DOM.getElement("new_showas").value;
    var ta = MochiKit.DOM.getElementsByTagAndClassName("textarea")[0];
    var cursorPos = ta.selectionEnd;
    var newCursorPos = cursorPos + showas.length + 4;
    var oldText = ta.value;
    var newText = oldText.slice(0, cursorPos) 
     + '`' + showas + '`_ '
     + oldText.slice(cursorPos);
    if (link.length > 3) 
    {
        if (link.slice(0, 7) != "http://")
        {
            link = "http://" + link;
        }
        newText = newText + "\n\n.. _`" + showas + "`: " + link;
    }
    ta.value = newText;
    showControlMenu();
    ta.focus();
    ta.selectionBegin = newCursorPos;
    ta.selectionEnd = newCursorPos;
}

showInsertImage = function(event) {
    alert('inserting');
}

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


