function onEdit(e) {
    // Fetch the URL from Script Properties
    var url = PropertiesService.getScriptProperties().getProperty('SYNC_POSTGRES_URL'); 

    var options = {
        'method': 'POST',
        'contentType': 'application/json'
    };
    UrlFetchApp.fetch(url, options);
}
