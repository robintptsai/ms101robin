$(function(){
	var submitting = false;
	var $info = $('.msg');
	function show(text){
		$info.html(text);
		submitting = false;
	}
	$('#del-token').click(function(){
		if (!submitting) {
			submitting = true;
			$.ajax({
				'type': 'POST',
				'error': function(){
					show('Sorry, submit failed duo to unknown reason.');
				},
				'success': show,
				'timeout': 10000
			});
		}
	});
});