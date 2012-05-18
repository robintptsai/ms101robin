(function(){
	var submitting = false;
	var $form = $('#profileform');
	$form.submit(function() {
		if (submitting) return false;
		submitting = true;
		$.ajax({
			'data': $form.serialize(),
			'type': 'POST',
			'error': function(){
				submitting = false;
				msgbbox('Sorry, save failed duo to unknown reason.');
			},
			'success': function(text){
				msgbbox(text);
				submitting = false;
			},
			'timeout': 10000
		});
		return false;
	});
})();