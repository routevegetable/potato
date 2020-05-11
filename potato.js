"use strict";


var codeTextArea = document.getElementById('code-text')
var codeOutputBox = document.getElementById('code-output')
var reloadButton = document.getElementById('reload-button')
var saveButton = document.getElementById('save-button')
var varAddButton = document.getElementById('var-add-button')
var widgetTypeSelect = document.getElementById('widget-types')
var cmObj;

// 1 seconds from edit to upload
var UPLOAD_DELAY = 1000
var uploadTimeout = null

// 0.5 seconds between widget refreshes
var REFRESH_DELAY = 500

// List of {name: "variable name", type: "widget type", other_prop: blah, element: element, ... }
var widgets = []

// Map from type -> { init: function(parent, obj) => element,
// set: function(obj, current_value);
// get: function(obj) }
var widgetTypes = {}

// Data to feed widgets
var progVars = {}

function appendCodeOutput(text, color) {
  var lines = text.split(/\n/)
  if(lines.length == 1 && lines[0].length == 0)
    return

  var date = new Date().toLocaleTimeString()
  var html = '<span style="color:' + color + '">'
  for(var i in lines) {
    html = html + '[' + date + '] ' + lines[i] + '<br>'
  }
  html = html + '</span>'
  codeOutputBox.innerHTML = codeOutputBox.innerHTML + html
  codeOutputBox.scrollTop = codeOutputBox.scrollHeight
}


/* This is used to edit widgets - all widget edits'
 * putVar calls go through here.
 * When there's nothing pending - we can instead
 * periodically update all the widgets */
var arl = new AsyncRateLimiter;


async function putVar(name, obj) {
  var resp = await fetch('/vars/' + name, {
    method: 'post',
    body: JSON.stringify(obj)
  })

  return await resp.json()
}

async function beginUploadCode() {
  uploadTimeout = null

  await putVar('code', cmObj.getValue())

  await beginUploadLayout()

  appendCodeOutput('Uploaded', 'green')

  //reloadButton.disabled = false
  //saveButton.disabled = false
}


// Schedule an upload
function scheduleUpload() {
  //reloadButton.disabled = true
  //saveButton.disabled = true

  // Clear any code upload timer we have
  if(uploadTimeout != null) clearTimeout(uploadTimeout)
  else appendCodeOutput('Edited - waiting to upload', 'aqua')

  // Start a new upload timer
  uploadTimeout = setTimeout(() => beginUploadCode(), UPLOAD_DELAY)

}

async function beginDownloadJson(path) {
  var resp = await fetch(path)
  return await resp.json()
}

// Download code to text area
async function beginDownloadCode() {
  var data = await beginDownloadJson('/vars/code')

  cmObj.setValue(data)

  // Set up edit handler
  cmObj.on('change', () => {
    scheduleUpload()
  })
}

function addWidgetToDOM(widget) {
  var widgetType = widgetTypes[widget.type]
  widget.element = widgetType.createElement()
  document.getElementById('widgets').appendChild(widget.element)

  widget.element.querySelector('.delete-widget').addEventListener('click', () => {
    widgets = widgets.filter(w => w != widget)
    widget.element.remove()
    beginUploadLayout()
  })

  // Post-add initialization
  widgetType.prepare(widget)

  widget.element.addEventListener('input', () => {
    arl.submit(() => putVar(widget.name, widgetType.get(widget)))
  })
}



async function beginUpdateWidgetData() {

  var data = await beginDownloadJson('/vars')

  /* Don't update widget data if we have an edit
   * pending */
  if(arl.doingThing)
    return;

  for(var i in widgets) {
    var widget = widgets[i]
    var widgetType = widgetTypes[widget.type]

    var value = data[widget.name]

    widgetType.set(widget, value)
  }
}

async function beginDownloadLayout() {

  // Download the widgets
  widgets = await beginDownloadJson('/vars/layout')

  if(widgets == null) {
    widgets = []
  }

  // Create the widgets in the DOM
  for(var i in widgets) {
    var widget = widgets[i]

    addWidgetToDOM(widget)

  }

  // Do a data update for all widgets
  await beginUpdateWidgetData()

  appendCodeOutput('Updated Widget Data', 'aqua')

}

async function beginUploadLayout() {

  var widgetsToUpload = []
  for(var i in widgets) {

    var copy = Object.assign({}, widgets[i])

    // Don't want this prop
    delete copy.element

    widgetsToUpload.push(copy)
  }

  await putVar('layout', widgetsToUpload)
}

function addNewWidget(name, type) {

  var widget = { type: type, name: name}

  widgets.push(widget)
  addWidgetToDOM(widget)

  beginUpdateWidgetData()

  beginUploadLayout()
}

document.addEventListener('DOMContentLoaded', () => {
  cmObj = CodeMirror(codeTextArea, {
    lineNumbers: true,
    mode: 'text/x-csrc'
  })
  cmObj.setSize("100%", "100%");

  beginDownloadCode()
  beginDownloadLayout()

  reloadButton.addEventListener('click', async function() {
    appendCodeOutput('Reloading...', 'aqua')
    var resp = await fetch('/reload')
    var json = await resp.json()
    //reloadButton.disabled = true

    appendCodeOutput(json.stdout, 'gray')
    appendCodeOutput(json.stderr, 'red')
    if(json.returncode == 0)
      appendCodeOutput('Reload Success', 'green')
    else
      appendCodeOutput('Reload Failed with error ' + json.returncode, 'red')
  })

  saveButton.addEventListener('click', async function(){
    appendCodeOutput('Saved', 'green')
    await fetch('/save')
    //saveButton.disabled = true
  })

  varAddButton.addEventListener('click', () => {
    var name = window.prompt("Enter name of variable")
    addNewWidget(name, widgetTypeSelect.value)
  })

  /* Periodically update widget data
   * if there's no async edity stuff pending */
  async function backgroundUpdate() {
    await beginUpdateWidgetData()
    setTimeout(backgroundUpdate, REFRESH_DELAY)
  }
  backgroundUpdate();
})



widgetTypes = {
  'Float Slider': {
    createElement: () => {
      var html = `
<header><button class='delete-widget'>X</button> <span class="name"></span>:<span class="value">?</span></header>
<input type="range">`
      var el = document.createElement('div')
      el.className = "float-slider widget"
      el.innerHTML = html
      el.addEventListener('input', () => {
        el.querySelector('span.value').innerText = el.querySelector('input').value
      })
      el.querySelector('span.value').innerText = el.querySelector('input').value
      return el
    },
    prepare: (obj) => {
      if(!obj.hasOwnProperty('configured')) {
        obj.min = parseFloat(window.prompt('Min'))
        obj.max = parseFloat(window.prompt('Max'))
        obj.configured = true
      }
      obj.element.querySelector('span.name').innerText = obj.name
      obj.element.querySelector('input').min = obj.min
      obj.element.querySelector('input').max = obj.max
      obj.element.querySelector('span.value').innerText = obj.element.querySelector('input').value
    },
    get: (obj) => {
      return parseFloat(obj.element.querySelector('input').value)
    },
    set: (obj, value) => {
      obj.element.querySelector('input').value = value
      obj.element.querySelector('span.value').innerText = obj.element.querySelector('input').value
    }
  },
  'Color Picker': {
    createElement: () => {
      var html = `
<header><button class='delete-widget'>X</button> <span class="name"></span>:</header>
<button class="jscolor {onFineChange: \'jsColorUpdate(this)\'}" value="ab2567">`
      var el = document.createElement('div')
      el.className = "color-picker widget"
      el.innerHTML = html
      return el
    },
    prepare: (obj) => {
      obj.element.querySelector('span.name').innerText = obj.name
      window.jscolor.installByClassName('jscolor');
      obj.element.querySelector('.jscolor').jscolor.widget = obj
    },
    get: (obj) => {
      var input = obj.element.querySelector('button.jscolor')
      var bigint = parseInt(input.jscolor.toHEXString().slice(1,7), 16)
      var r = (bigint >> 16) & 255;
      var g = (bigint >> 8) & 255;
      var b = bigint & 255;
      return r | (g << 8) | (b << 16)
    },
    set: (obj, value) => {

      var input = obj.element.querySelector('button.jscolor')
      var bigInt = parseInt(input.jscolor.toHEXString().slice(1,7), 16)
      var r = value & 0xFF;
      var g = (value >> 8) & 0xFF;
      var b = (value >> 16) & 0xFF;
      input.jscolor.fromRGB(r,g,b)
    }
  },
  'Choice': {
    createElement: () => {
      var html = `
<header><button class='delete-widget'>x</button> <span class="name"></span>:</header>
<select></select>`
      var el = document.createElement('div')
      el.className = "choice widget"
      el.innerHTML = html
      return el
    },
    prepare: (obj) => {
      if(!obj.hasOwnProperty('configured')) {
        var choiceString = window.prompt('Input list of choices, thing=number, thing=number')

        obj.choices = []
        var parts = choiceString.split(',')
        for(var i in parts) {
          var part = parts[i].trim()

          var tuple = part.split('=')
          var thing = tuple[0]
          var number = parseInt(tuple[1])
          obj.choices.push([thing, number])
        }
        obj.configured = true
      }

      for(var i in obj.choices) {
        var opt = document.createElement('option')
        opt.innerText = obj.choices[i][0]
        opt.value = obj.choices[i][1]
        obj.element.querySelector('select').appendChild(opt)
      }

      obj.element.querySelector('span.name').innerText = obj.name
    },

    get: (obj) => {
      return parseInt(obj.element.querySelector('select').value)
    },
    set: (obj, value) => {
      obj.element.querySelector('select').value = value
    }
  },
  'Switch': {
    createElement: () => {
      var html = `
<header><button class='delete-widget'>X</button> <span class="name"></span>:</span></header>
<input type="checkbox">`
      var el = document.createElement('div')
      el.className = "switch widget"
      el.innerHTML = html
      return el
    },
    prepare: (obj) => {
      obj.element.querySelector('span.name').innerText = obj.name
    },
    get: (obj) => {
      return obj.element.querySelector('input').checked ? 1 : 0
    },
    set: (obj, value) => {
      obj.element.querySelector('input').checked = (value == 1)
    }
  },
}

function jsColorUpdate(jscolor) {
  var widget = jscolor.widget
  var widgetType = widgetTypes[widget.type]
  arl.submit(() => putVar(widget.name, widgetType.get(widget)));
}




function AsyncRateLimiter() {
  /* Operation is in progress */
  this.doingThing = false;

  /* Next operation to do after this one */
  this.nextFn = false;
}

AsyncRateLimiter.prototype.submit = function(fn) {
  var instance = this;

  if(!instance.doingThing) {
    instance.doingThing = true;

    function doNext() {
      /* Do the next thing if there is one */
      if(instance.nextFn) {
        var p = instance.nextFn();
        instance.nextFn = null;
        p.then(doNext);
      } else {
        instance.doingThing = false;
      }
    }

    /* Do it immediately */
    fn().then(doNext);

  } else {
    /* Do it next, dropping whatever was there */
    instance.nextFn = fn;
  }
}
