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
  widget.element = widgetType.init(document.getElementById('widgets'), widget)

  widget.element.addEventListener('input', () => {
    putVar(widget.name, widgetType.get(widget))
  })


  widget.element.querySelector('.delete-widget').addEventListener('click', () => {
    widgets = widgets.filter(w => w != widget)
    widget.element.remove()
    beginUploadLayout()
  })
}

async function beginUpdateWidgetData() {

  var data = await beginDownloadJson('/vars')

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
})



widgetTypes = {
  'Float Slider': {
    init: (parent, obj) => {
      if(!obj.hasOwnProperty('configured')) {
        obj.min = parseFloat(window.prompt('Min'))
        obj.max = parseFloat(window.prompt('Max'))
        obj.configured = true
      }
      var html = `
<header><button class='delete-widget'>X</button> ${obj.name}:<span class="value">?</span></header>
<input type="range" min="${obj.min}" max="${obj.max}">`
      var el = document.createElement('div')
      el.className = "float-slider widget"
      el.innerHTML = html
      parent.appendChild(el)
      el.addEventListener('input', () => {
        el.querySelector('span.value').innerText = el.querySelector('input').value
      })
      el.querySelector('span.value').innerText = el.querySelector('input').value
      return el
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
    init: (parent, obj) => {
      if(!obj.hasOwnProperty('configured')) {
        obj.min = parseFloat(window.prompt('Min'))
        obj.max = parseFloat(window.prompt('Max'))
        obj.configured = true
      }
      var html = `
<header><button class='delete-widget'>X</button> ${obj.name}:</header>
<input class="jscolor {onFineChange: \'jsColorUpdate(this)\'}" value="ab2567">`
      var el = document.createElement('div')
      el.className = "color-picker widget"
      el.innerHTML = html
      parent.appendChild(el)
      window.jscolor.installByClassName('jscolor');
      el.querySelector('.jscolor').jscolor.widget = obj
      return el
    },
    get: (obj) => {
      var input = obj.element.querySelector('input')
      var bigint = parseInt(input.jscolor.toHEXString().slice(1,7), 16)
      var r = (bigint >> 16) & 255;
      var g = (bigint >> 8) & 255;
      var b = bigint & 255;
      return r | (g << 8) | (b << 16)
    },
    set: (obj, value) => {

      var input = obj.element.querySelector('input')
      var bigInt = parseInt(input.jscolor.toHEXString().slice(1,7), 16)
      var r = value & 0xFF;
      var g = (value >> 8) & 0xFF;
      var b = (value >> 16) & 0xFF;
      input.jscolor.fromRGB(r,g,b)
    }
  }
}

function jsColorUpdate(jscolor) {
  var widget = jscolor.widget
  var widgetType = widgetTypes[widget.type]
  putVar(widget.name, widgetType.get(widget))
}
