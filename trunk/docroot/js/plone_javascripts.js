// Heads up! August 2003  - Geir Bækholt
// This file now requires the javascript variable portal_url to be set 
// in the plone_javascript_variables.js file. Any other variables from Plone
// that you want to pass into these scripts should be placed there.

// 08-17-2004: Alex changed so that the search highlighting is done in a single
//  pass for multiple-word queries.  Makes it abou 2x as fast.
//  Also made it so that it works in Safari, by not using RegEx.
//  Also made it so that the word has to match the beginning.
// 08-23-2004: Alex made it so that highlights won't occur inside textarea's,
//  since this makes a mess in Firefox (works in IE).
// 01-21-2005: Pierre disabled scanning for links because it's way too slow on
//  long discussions. Also removed a bunch of code we weren't using. Also embed
//  contents of plone_menu.js in this file.

function registerPloneFunction(func){
    // registers a function to fire onload. 
	// Turned out we kept doing this all the time
	// Use this for initilaizing any javascript that should fire once the page has been loaded. 
	// 
    if (window.addEventListener) window.addEventListener("load",func,false);
    else if (window.attachEvent) window.attachEvent("onload",func);   
  }

function getContentArea(){
	// to end all doubt on where the content sits. It also felt a bit silly doing this over and over in every
	// function, even if it is a tiny operation. Just guarding against someone changing the names again, in the name
	// of semantics or something.... ;)
	node =  document.getElementById('region-content')
	if (! node){
		node = document.getElementById('content')
		}
	return node
	}



function climb(node, words){
	 // traverse childnodes
    if (! node){return false}
    if (node.hasChildNodes) {
		var i;
		for (i=0;i<node.childNodes.length;i++) {
            climb(node.childNodes[i],words);
		}
        if (node.nodeType == 3){
            checkforhighlight(node, words, 0);
           // check all textnodes. Feels inefficient, but works
        }
}

// helper function for matching only beginning of words
function isAlpha(c) {
    c = c.toLowerCase();
    return !((c < 'a') || (c > 'z'));
    }
  
function checkforhighlight(node,words,start) {
    for (q=start;q<words.length;q++) {
        word = words[q];
        ind = node.nodeValue.toLowerCase().indexOf(word)
        if (ind != -1) {
            // only match the beginning of words
            if ((ind == 0) || (!isAlpha(node.nodeValue.charAt(ind-1)))) {
                if ((node.parentNode.className != "highlightedSearchTerm") && (node.parentNode.nodeName.toLowerCase() != "textarea")) {
                    
                    par = node.parentNode;
                    contents = node.nodeValue;
                
                    // make 3 shiny new nodes
                    hiword = document.createElement("span");
                    hiword.className = "highlightedSearchTerm";
                    hiword.appendChild(document.createTextNode(contents.substr(ind,word.length)));

                    prefixNode = document.createTextNode(contents.substr(0,ind))
                    suffixNode = document.createTextNode(contents.substr(ind+word.length))
                    par.insertBefore(prefixNode,node);
                    par.insertBefore(hiword,node);
                    par.insertBefore(suffixNode,node);

                    par.removeChild(node);

                    checkforhighlight(prefixNode, words, q+1);   // otherwise it won't get checked
                    // checkforhighlight(suffixNode, words);
                    }
                }
            }
        }
    }
  
}


// 08-17-2004: Alex: these are from lucene, but I also added "not"
STOP_WORDS = new Array("0", "1", "2", "3", "4", "5", "6", "7", "8",
        "9", "000", "$",
        "about", "after", "all", "also", "an", "and",
        "another", "any", "are", "as", "at", "be",
        "because", "been", "before", "being", "between",
        "both", "but", "by", "came", "can", "come",
        "could", "did", "do", "does", "each", "else",
        "for", "from", "get", "got", "has", "had",
        "he", "have", "her", "here", "him", "himself",
        "his", "how","if", "in", "into", "is", "it",
        "its", "just", "like", "make", "many", "me",
        "might", "more", "most", "much", "must", "my",
        "never", "now", "of", "on", "only", "or",
        "other", "our", "out", "over", "re", "said",
        "same", "see", "should", "since", "so", "some",
        "still", "such", "take", "than", "that", "the",
        "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "to", "too",
        "under", "up", "use", "very", "want", "was",
        "way", "we", "well", "were", "what", "when",
        "where", "which", "while", "who", "will",
        "with", "would", "you", "your",
        "a", "b", "c", "d", "e", "f", "g", "h", "i",
        "j", "k", "l", "m", "n", "o", "p", "q", "r",
        "s", "t", "u", "v", "w", "x", "y", "z", "not");

function isStopWord(word) {
    numstop = STOP_WORDS.length;
    for (i=0; i<numstop; i++) {
        if (STOP_WORDS[i] == word) {
            return true;
            }
        }
    return false;
    }

function highlightSearchTerm() {
        // search-term-highlighter function --  Geir Bækholt
        query = window.location.search
        // _robert_ ie 5 does not have decodeURI 
        if (typeof decodeURI != 'undefined'){
            query = decodeURI(unescape(query)) // thanks, Casper 
        }
        else {
            return false
        }
        if (query){
            // 08-17-2004: Alex made it so that we don't use RegEx, because Safari blows up
            beg = query.indexOf("searchterm=");
            if (beg == -1) {
                return false;
                }
            end = query.indexOf("&", beg);
            if (end == -1) {
                end = query.length + 1;
                }
            query = query.substring(beg+11, end)
            if (query) {
                queries = query.replace(/\+/g,' ').split(/\s+/)

                // 08-17-2004: Alex made it so that search boolean operators and stop words don't get highlighted.
                //  Also make the words lowercase here rather than doing it over and over again in
                //  checkforhighlight()
                filtered_queries = new Array()
                for (q=0; q<queries.length; q++) {
                    query = queries[q].toLowerCase();
                    if (!isStopWord(query)) {
                        filtered_queries[filtered_queries.length] = query;
                        }
                    }
                
                // make sure we start the right place and not higlight menuitems or breadcrumb
                contentarea = getContentArea();
                climb(contentarea, filtered_queries);
            }
        }
}
registerPloneFunction(highlightSearchTerm);


// ----------------------------------------------
// StyleSwitcher functions written by Paul Sowden
// http://www.idontsmoke.co.uk/ss/
// - - - - - - - - - - - - - - - - - - - - - - -
// For the details, visit ALA:
// http://www.alistapart.com/stories/alternate/
// ----------------------------------------------

function setActiveStyleSheet(title, reset) {
  var i, a, main;
  for(i=0; (a = document.getElementsByTagName("link")[i]); i++) {
    if(a.getAttribute("rel").indexOf("style") != -1 && a.getAttribute("title")) {
      a.disabled = true;
      if(a.getAttribute("title") == title) a.disabled = false;
    }
  }
  if (reset == 1) {
  createCookie("wstyle", title, 365);
  }
}

function setStyle() {
var style = readCookie("wstyle");
if (style != null) {
setActiveStyleSheet(style, 0);
}
}

function createCookie(name,value,days) {
  if (days) {
    var date = new Date();
    date.setTime(date.getTime()+(days*24*60*60*1000));
    var expires = "; expires="+date.toGMTString();
  }
  else expires = "";
  document.cookie = name+"="+escape(value)+expires+"; path=/;";
}

function readCookie(name) {
  var nameEQ = name + "=";
  var ca = document.cookie.split(';');
  for(var i=0;i < ca.length;i++) {
    var c = ca[i];
    while (c.charAt(0)==' ') c = c.substring(1,c.length);
    if (c.indexOf(nameEQ) == 0) return unescape(c.substring(nameEQ.length,c.length));
  }
  return null;
}
registerPloneFunction(setStyle);


// Do *NOT* depend on this menu code, it *will* be rewritten in later versions
// of Plone. This is a quick fix that will be replaced with something more
// elegant later.

/*




*/
// Code to determine the browser and version.

function Browser() {
    var ua, s, i;
    
    this.isIE = false; // Internet Explorer
    this.isNS = false; // Netscape
    this.version = null;
    
    ua = navigator.userAgent;
    
    s = "MSIE";
    if ((i = ua.indexOf(s)) >= 0) {
        this.isIE = true;
        this.version = parseFloat(ua.substr(i + s.length));
        return;
    }  
    s = "Netscape6/";
    if ((i = ua.indexOf(s)) >= 0) {
        this.isNS = true;
        this.version = parseFloat(ua.substr(i + s.length));
        return;
    }
    
    // Treat any other "Gecko" browser as NS 6.1.
    
    s = "Gecko";
    if ((i = ua.indexOf(s)) >= 0) {
        this.isNS = true;
        this.version = 6.1;
        return;
    }
}
var browser = new Browser();

// Code for handling the menu bar and active button.
var activeButton = null;

// Capture mouse clicks on the page so any active button can be
// deactivated.

if (browser.isIE){
    document.onmousedown = pageMousedown;
}else{
    document.addEventListener("mousedown", pageMousedown, true);
}

function pageMousedown(event) {
    
    var el;
    
    // If there is no active button, exit.
    
    if (activeButton == null){
        return;
        }
    
    // Find the element that was clicked on.
    
    if (browser.isIE){
        el = window.event.srcElement;
    }else{
        el = (event.target.tagName ? event.target : event.target.parentNode);
    }
    // If the active button was clicked on, exit.
    
    if (el == activeButton){
        return
        };
    
    // If the element is not part of a menu, reset and clear the active
    // button.
    
    if (getContainerWith(el, "UL", "actionMenu") == null) {
        resetButton(activeButton);
        activeButton = null;
    }
}

function buttonClick(event, menuId) {
    
    var button;
    
    // Get the target button element.
    
    if (browser.isIE){
        button = window.event.srcElement;
    }else{
        if (event)
          button = event.currentTarget;
        else
          return false;
    }
    // Blur focus from the link to remove that annoying outline.
    
    button.blur();
    
    // Associate the named menu to this button if not already done.
    // Additionally, initialize menu display.
    
    if (button.menu == null) {
        button.menu = document.getElementById(menuId);
        if (button.menu.isInitialized == null) {
            menuInit(button.menu);
        }
    }
    
    // Reset the currently active button, if any.
    
    if (activeButton != null){
        resetButton(activeButton);
        }
    // Activate this button, unless it was the currently active one.
    
    if (button != activeButton) {
        depressButton(button);
        activeButton = button;
    }else{
        activeButton = null;
    }
    return false;
}

function buttonMouseover(event, menuId) {

    var button;
    
    // Find the target button element.
    
    if (browser.isIE){
        button = window.event.srcElement;
    }else{
        button = event.currentTarget;
    }
    // If any other button menu is active, make this one active instead.
    
    if (activeButton != null && activeButton != button){
        buttonClick(event, menuId);
        }
}

function depressButton(button) {

    var x, y;
    
    // Update the button's style class to make it look like it's
    // depressed.
    
    button.className += " menuButtonActive";
    
    // Make the associated drop down menu visible
    
    vis = button.menu.style.visibility;
    button.menu.style.visibility = (vis == "hidden" || vis == '') ? "visible" : "hidden";
}

function resetButton(button) {

    // Restore the button's style class.
    
    removeClassName(button, "menuButtonActive");
    
    // Hide the button's menu, first closing any sub menus.
    
    if (button.menu != null) {
        closeSubMenu(button.menu);
        button.menu.style.visibility = "hidden";
    }
}

// Code to handle the menus and sub menus.

function menuMouseover(event) {
    
    var menu;
    
    // Find the target menu element.
    
    if (browser.isIE){
        menu = getContainerWith(window.event.srcElement, "UL", "actionMenu");
    }else{
        menu = event.currentTarget;
    }
    
    // Close any active sub menu.
    
    if (menu.activeItem != null){
        closeSubMenu(menu);
        }
}

function menuItemMouseover(event, menuId) {

    var item, menu, x, y;
    
    // Find the target item element and its parent menu element.
    
    if (browser.isIE){
        item = getContainerWith(window.event.srcElement, "LI", "menuItem");
    }else{
        item = event.currentTarget;
        menu = getContainerWith(item, "UL", "menu");
    }
    // Close any active sub menu and mark this one as active.
    
    if (menu.activeItem != null){
        closeSubMenu(menu);
        menu.activeItem = item;
    }
    
    // Highlight the item element.
    
    item.className += " menuItemHighlight";
    
    // Initialize the sub menu, if not already done.
    
    if (item.subMenu == null) {
        item.subMenu = document.getElementById(menuId);
        if (item.subMenu.isInitialized == null){
            menuInit(item.subMenu);
            }
    }
    
    // Get position for submenu based on the menu item.
    
    x = getPageOffsetLeft(item) + item.offsetWidth;
    y = getPageOffsetTop(item);
    
    // Adjust position to fit in view.
    
    var maxX, maxY;
    
    if (browser.isNS) {
        maxX = window.scrollX + window.innerWidth;
        maxY = window.scrollY + window.innerHeight;
    }
    else if (browser.isIE) {
        maxX = (document.documentElement.scrollLeft != 0 ? document.documentElement.scrollLeft : document.body.scrollLeft)
        + (document.documentElement.clientWidth != 0 ? document.documentElement.clientWidth : document.body.clientWidth);
        maxY = (document.documentElement.scrollTop != 0 ? document.documentElement.scrollTop : document.body.scrollTop)
        + (document.documentElement.clientHeight != 0 ? document.documentElement.clientHeight : document.body.clientHeight);
    }
    maxX -= item.subMenu.offsetWidth;
    maxY -= item.subMenu.offsetHeight;
    
    if (x > maxX){
        x = Math.max(0, x - item.offsetWidth - item.subMenu.offsetWidth  + (menu.offsetWidth - item.offsetWidth));
        y = Math.max(0, Math.min(y, maxY));
    }
    // Position and show it.
    
    item.subMenu.style.left = x + "px";
    item.subMenu.style.top = y + "px";
    item.subMenu.style.visibility = "visible";
    
    // Stop the event from bubbling.
    
    if (browser.isIE){
        window.event.cancelBubble = true;
    }else{
        event.stopPropagation();
    }
}

function closeSubMenu(menu) {
    
    if (menu == null || menu.activeItem == null)
    return;
    
    // Recursively close any sub menus.
    
    if (menu.activeItem.subMenu != null) {
    closeSubMenu(menu.activeItem.subMenu);
    menu.activeItem.subMenu.style.visibility = "hidden";
    menu.activeItem.subMenu = null;
    }
    removeClassName(menu.activeItem, "menuItemHighlight");
    menu.activeItem = null;
}

// Code to initialize menus.

function menuInit(menu) {
    
    var itemList, spanList;
    var textEl, arrowEl;
    var itemWidth;
    var w, dw;
    var i, j;
    
    // For IE, replace arrow characters.
    
    if (browser.isIE) {
        menu.style.lineHeight = "2.5ex";
        spanList = menu.getElementsByTagName("SPAN");
        for (i = 0; i < spanList.length; i++)
        if (hasClassName(spanList[i], "menuItemArrow")) {
            spanList[i].style.fontFamily = "Webdings";
            spanList[i].firstChild.nodeValue = "4";
        }
    }
    
    // Find the width of a menu item.
    
    itemList = menu.getElementsByTagName("A");
    if (itemList.length > 0){
        itemWidth = itemList[0].offsetWidth;
    }else{
        return;
    }
    // For items with arrows, add padding to item text to make the
    // arrows flush right.
    
    for (i = 0; i < itemList.length; i++) {
        spanList = itemList[i].getElementsByTagName("A");
        textEl = null;
        arrowEl = null;
        for (j = 0; j < spanList.length; j++) {
        if (hasClassName(spanList[j], "menuItemText")){
            textEl = spanList[j];
            }
        if (hasClassName(spanList[j], "menuItemArrow")){
            arrowEl = spanList[j];
            }
        }
        if (textEl != null && arrowEl != null){
        textEl.style.paddingRight = (itemWidth - (textEl.offsetWidth + arrowEl.offsetWidth)) + "px";
        }
    }
    
    // Fix IE hover problem by setting an explicit width on first item of
    // the menu.
    
    if (browser.isIE) {
        w = itemList[0].offsetWidth;
        itemList[0].style.width = w + "px";
        dw = itemList[0].offsetWidth - w;
        w -= dw;
        itemList[0].style.width = w + "px";
    }
    
    // Mark menu as initialized.
    
    menu.isInitialized = true;
}

// General utility functions.

    function getContainerWith(node, tagName, className) {
    
    // Starting with the given node, find the nearest containing element
    // with the specified tag name and style class.
    
    while (node != null) {
        if (node.tagName != null && node.tagName == tagName && hasClassName(node, className)){
            return node;
    }
    node = node.parentNode;
    }
    return node;
}

    function hasClassName(el, name) {
    
    var i, list;
    
    // Return true if the given element currently has the given class
    // name.
    
    list = el.className.split(" ");
    for (i = 0; i < list.length; i++)
    if (list[i] == name){
        return true;
        }
    return false;
}

function removeClassName(el, name) {
    
    var i, curList, newList;
    
    if (el.className == null){
        return;
        }
    // Remove the given class name from the element's className property.
    
    newList = new Array();
    curList = el.className.split(" ");
    for (i = 0; i < curList.length; i++){
        if (curList[i] != name){
            newList.push(curList[i]);
            el.className = newList.join(" ");
        }
    }
}
function getPageOffsetLeft(el) {

var x;

// Return the x coordinate of an element relative to the page.

x = el.offsetLeft;
if (el.offsetParent != null)
x += getPageOffsetLeft(el.offsetParent);

return x;
}

function getPageOffsetTop(el) {
    
    var y;
    
    // Return the x coordinate of an element relative to the page.
    
    y = el.offsetTop;
    if (el.offsetParent != null){
        y += getPageOffsetTop(el.offsetParent);
    }
    return y;
}
