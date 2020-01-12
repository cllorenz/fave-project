stateEnum = {
	G_LOAD  : 0,
	G_OVIEW  : 1,
	G_RESULT  : 2
};

headerEnum = {
	STEP1 : 'Load Files (step 1 of 3)',
	STEP2 : 'Overview (step 2 of 3)',
	STEP3 : 'Results (step 3 of 3)',
};

instance = "";

if (typeof(state) == 'undefined' || state == null) {
	state = stateEnum.G_LOAD;
}

var loadNext = function() {
	switch(state) {
	case stateEnum.G_LOAD:
		state = stateEnum.G_OVIEW;
		var btn = document.getElementById('bck');
		btn.hidden = false;
		var ldBox = document.getElementById('ldBox');
		ldBox.hidden = true;
		var canBox = document.getElementById('canBox');
		canBox.hidden = false;
		var legendBox = document.getElementById('legendBox');
		legendBox.hidden = false;
		var header = document.getElementById('mainHead');
		header.innerHTML = headerEnum.STEP2;
		colored = false;
		//drawView();
		//var file = document.getElementById('file1');
		//var fr = new FileReader();
		//var policy = fr.readAsText(file.input);
		//instance = handleParser(policy);
		//instance = handleAggregator(instance);
		break;
	case stateEnum.G_OVIEW:
		state = stateEnum.G_RESULT;
		var btn = document.getElementById('nxt');
		btn.hidden = true;
		var header = document.getElementById('mainHead');
		header.innerHTML = headerEnum.STEP3;
		//instance = handleInstantiator(instance);
		//instance = handleSolver(instance);
		colored = true;
		//drawView();
		break;
	case stateEnum.G_RESULT:
		break;
	default:
		state = stateEnum.G_LOAD;
		break;
	};
};

var loadBack = function() {
	switch(state) {
	case stateEnum.G_LOAD:
		break;
	case stateEnum.G_OVIEW:
		state = stateEnum.G_LOAD;
		var btn = document.getElementById('bck');
		btn.hidden = true;
		var ldBox = document.getElementById('ldBox');
		ldBox.hidden = false;
		var canBox = document.getElementById('canBox');
		canBox.hidden = true;
		var legendBox = document.getElementById('legendBox');
		legendBox.hidden = true;
		var header = document.getElementById('mainHead');
		header.innerHTML = headerEnum.STEP1;
		//drawView();
		break;
	case stateEnum.G_RESULT:
		state = stateEnum.G_OVIEW;
		var btn = document.getElementById('nxt');
		btn.hidden = false;
		var header = document.getElementById('mainHead');
		header.innerHTML = headerEnum.STEP2;
		colored = false;
		drawView();
		break;
	default:
		state = stateEnum.G_LOAD;
		break;
	};
};

var addInput = function () {
	var par = document.getElementById('ldBox');
	var index = par.lastElementChild.id.substr(4);

	var newElem = document.createElement('input');
	newElem.id = 'file'+(parseInt(index)+1);
	newElem.setAttribute('type','file');
	newElem.setAttribute('value','');
	newElem.setAttribute('onchange','addInput(this)');

	var newDiv = document.createElement('div');
	newDiv.appendChild(newElem);
	newDiv.setAttribute('type','tbox');

	par.appendChild(newDiv);
};

var handleParser = function(policy) {
	return postToURL('/parser',{'policy' : txt},'post');
};

var handleAggregatorGet = function() {
	return postToURL('/aggregator',{},'get');
};

var handleAggregatorPost = function(params) {
	return postToURL('/aggregator',params,'post');
};

var handleInstantiator = function(params) {
	return postToURL('/instantiator',params,'post');
};

var handleSolver = function(instance) {
	return postToURL('/solver',{'instance':instance},'post');
};

var postToURL = function(path,values,method) {
	var method = method || 'post';
	var values = values || {};

	var form = document.createElement('form');
	form.setAttribute('method',method);
	form.setAttribute('action',path);

	for(var key in params) {
		if(params.hasOwnPropertyKey(key)) {
			var hiddenField = document.createElement('input');
			hiddenField.setAttribute('type','hidden');
			hiddenField.setAttribute('name',key);
			hiddenField.setAttribute('value',params[key]);

			form.appendChild(hiddenField);
		}
	};

	document.body.appendChild(form);
	return form.submit();
};

check = true;

var toggleCheck = function() {
	if (check) {
		check = false;
		if (state == stateEnum.G_RESULT) {
			colored = false;
		};
	} else {
		check = true;
		if (state == stateEnum.G_RESULT) {
			colored = true;
		};
	};
	drawView();
};
