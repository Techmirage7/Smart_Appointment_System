// Utility Functions
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString(undefined, options);
}

function formatTime(timeString) {
    return new Date(`2000-01-01T${timeString}`).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Booking Functions
function cancelBooking(bookingId) {
    if (!confirm('Are you sure you want to cancel this booking? This action cannot be undone.')) {
        return;
    }
    
    const reason = prompt('Please provide a reason for cancellation:', 'Schedule conflict');
    if (reason === null) {
        return; // User cancelled the prompt
    }
    
    const cancellationData = {
        reason: reason
    };
    
    fetch(`/api/bookings/${bookingId}/cancel`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(cancellationData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            showNotification('Booking cancelled successfully!', 'success');
            loadUserBookings();
            checkNotifications();
        }
    })
    .catch(error => {
        console.error('Error cancelling booking:', error);
        showNotification('Failed to cancel booking. Please try again.', 'error');
    });
}

function confirmBooking(bookingId) {
    fetch(`/api/bookings/${bookingId}/confirm`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        alert('Booking confirmed successfully');
        loadBookings();
    })
    .catch(error => {
        console.error('Error confirming booking:', error);
        alert('Error confirming booking');
    });
}

// Service Provider Functions
function approveProvider(providerId) {
    fetch(`/api/admin/providers/${providerId}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        alert('Service provider approved successfully');
        loadProviders();
    })
    .catch(error => {
        alert('Error approving service provider');
    });
}

function rejectProvider(providerId) {
    if (confirm('Are you sure you want to reject this service provider?')) {
        fetch(`/api/admin/providers/${providerId}/reject`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            alert('Service provider rejected successfully');
            loadProviders();
        })
        .catch(error => {
            alert('Error rejecting service provider');
        });
    }
}

// Form Validation
function validateForm(formId) {
    const form = document.getElementById(formId);
    const inputs = form.querySelectorAll('input[required], select[required]');
    let isValid = true;

    inputs.forEach(input => {
        if (!input.value) {
            isValid = false;
            input.classList.add('is-invalid');
        } else {
            input.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Add form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(form.id)) {
                e.preventDefault();
            }
        });
    });

    // Add input validation
    const inputs = document.querySelectorAll('input[required], select[required]');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            if (this.value) {
                this.classList.remove('is-invalid');
            }
        });
    });
});

// Notification System
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(notification, container.firstChild);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Date and Time Validation
function validateDateTime(date, time) {
    const selectedDateTime = new Date(`${date}T${time}`);
    const now = new Date();
    
    if (selectedDateTime < now) {
        showNotification('Please select a future date and time', 'warning');
        return false;
    }
    
    return true;
}

// Service Provider Availability Check
function checkProviderAvailability(providerId, date, time) {
    return fetch(`/api/providers/${providerId}/availability?date=${date}&time=${time}`)
        .then(response => response.json())
        .then(data => data.available)
        .catch(error => {
            console.error('Error checking provider availability:', error);
            return false;
        });
}

// Payment functions
function processPayment(bookingId, amount) {
    const paymentData = {
        booking_id: bookingId,
        amount: amount,
        payment_method: 'Credit Card'
    };

    fetch('/api/payments', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(paymentData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            showNotification('Payment processed successfully!', 'success');
            loadUserBookings();
            loadUserPayments();
        }
    })
    .catch(error => {
        console.error('Error processing payment:', error);
        showNotification('Failed to process payment. Please try again.', 'error');
    });
}

function loadUserPayments() {
    fetch('/api/user/payments')
        .then(response => response.json())
        .then(data => {
            if (Array.isArray(data)) {
                const paymentsTable = document.getElementById('payments-table-body');
                if (paymentsTable) {
                    paymentsTable.innerHTML = '';
                    
                    if (data.length === 0) {
                        paymentsTable.innerHTML = '<tr><td colspan="6" class="text-center">No payments found</td></tr>';
                        return;
                    }
                    
                    data.forEach(payment => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${payment.PaymentID || 'N/A'}</td>
                            <td>Booking #${payment.B_ID} - ${payment.service_name || 'N/A'}</td>
                            <td>${payment.PaymentDate || 'N/A'}</td>
                            <td>$${payment.Amount || '0.00'}</td>
                            <td>${payment.PaymentMethod || 'N/A'}</td>
                            <td>
                                <span class="badge badge-${payment.Status === 'Confirmed' ? 'success' : 'warning'}">${payment.Status || 'N/A'}</span>
                                ${payment.InvoiceID ? `<button class="btn btn-sm btn-outline-primary ml-2" onclick="viewInvoice(${payment.InvoiceID})">Invoice</button>` : ''}
                            </td>
                        `;
                        paymentsTable.appendChild(row);
                    });
                }
            } else if (data.error) {
                showNotification(data.error, 'error');
            }
        })
        .catch(error => {
            console.error('Error loading payments:', error);
            showNotification('Failed to load payments. Please try again.', 'error');
        });
}

function viewInvoice(invoiceId) {
    // You can implement this to open a modal with invoice details or redirect to an invoice page
    showNotification(`Viewing invoice #${invoiceId}`, 'info');
}

// Reviews
function submitReview(bookingId) {
    const rating = document.getElementById(`rating-${bookingId}`).value;
    const comment = document.getElementById(`comment-${bookingId}`).value;
    
    if (!rating) {
        showNotification('Please select a rating', 'error');
        return;
    }
    
    const reviewData = {
        booking_id: bookingId,
        rating: parseInt(rating),
        comment: comment
    };
    
    fetch('/api/reviews', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(reviewData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            showNotification(`Thank you for reviewing ${data.provider}!`, 'success');
            // Update UI to reflect the review has been submitted
            const reviewForm = document.getElementById(`review-form-${bookingId}`);
            if (reviewForm) {
                reviewForm.innerHTML = `
                    <div class="alert alert-success">
                        Review submitted (${data.rating} stars)
                    </div>
                `;
            }
        }
    })
    .catch(error => {
        console.error('Error submitting review:', error);
        showNotification('Failed to submit review. Please try again.', 'error');
    });
}

function loadProviderReviews(providerId) {
    fetch(`/api/provider/${providerId}/reviews`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification(data.error, 'error');
                return;
            }
            
            const reviewsContainer = document.getElementById('provider-reviews');
            if (!reviewsContainer) return;
            
            // Display average rating
            const ratingEl = document.getElementById('provider-rating');
            if (ratingEl) {
                ratingEl.textContent = `${data.average_rating} (${data.total_reviews} reviews)`;
            }
            
            reviewsContainer.innerHTML = '';
            
            if (data.reviews.length === 0) {
                reviewsContainer.innerHTML = '<div class="alert alert-info">No reviews yet</div>';
                return;
            }
            
            data.reviews.forEach(review => {
                const reviewEl = document.createElement('div');
                reviewEl.className = 'review-item mb-3 p-3 border rounded';
                reviewEl.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${review.customer_name || 'Anonymous'}</strong>
                            <span class="text-muted ml-2">${review.ReviewDate}</span>
                        </div>
                        <div class="rating">
                            ${'★'.repeat(review.Rating)}${'☆'.repeat(5 - review.Rating)}
                        </div>
                    </div>
                    <p class="mt-2 mb-0">${review.Comment || 'No comment provided'}</p>
                `;
                reviewsContainer.appendChild(reviewEl);
            });
        })
        .catch(error => {
            console.error('Error loading reviews:', error);
            showNotification('Failed to load reviews', 'error');
        });
}

// Services functions
function loadServices() {
    fetch('/api/services')
        .then(response => response.json())
        .then(data => {
            if (Array.isArray(data)) {
                const servicesSelect = document.getElementById('service-select');
                if (servicesSelect) {
                    servicesSelect.innerHTML = '<option value="">Select a service</option>';
                    
                    data.forEach(service => {
                        const option = document.createElement('option');
                        option.value = service.S_ID;
                        option.textContent = `${service.Name} - $${service.Price}`;
                        option.dataset.price = service.Price;
                        servicesSelect.appendChild(option);
                    });
                }
                
                const servicesContainer = document.getElementById('services-list');
                if (servicesContainer) {
                    servicesContainer.innerHTML = '';
                    
                    data.forEach(service => {
                        const serviceCard = document.createElement('div');
                        serviceCard.className = 'col-md-4 mb-4';
                        serviceCard.innerHTML = `
                            <div class="card">
                                <div class="card-body">
                                    <h5 class="card-title">${service.Name}</h5>
                                    <p class="card-text">${service.Description || 'No description available'}</p>
                                    <p class="card-text text-primary font-weight-bold">$${service.Price}</p>
                                    <button class="btn btn-primary" onclick="bookService(${service.S_ID}, '${service.Name}', ${service.Price})">Book Now</button>
                                </div>
                            </div>
                        `;
                        servicesContainer.appendChild(serviceCard);
                    });
                }
            } else if (data.error) {
                showNotification(data.error, 'error');
            }
        })
        .catch(error => {
            console.error('Error loading services:', error);
            showNotification('Failed to load services', 'error');
        });
}

function bookService(serviceId, serviceName, price) {
    // This function might show a booking form modal or redirect to booking page
    const bookingDate = prompt('Enter booking date (YYYY-MM-DD):', getTomorrowDate());
    if (!bookingDate) return;
    
    const bookingTime = prompt('Enter booking time (HH:MM):', '10:00');
    if (!bookingTime) return;
    
    createBooking(serviceId, bookingDate, bookingTime);
}

function getTomorrowDate() {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split('T')[0];
}

function createBooking(serviceId, bookingDate, bookingTime) {
    const bookingData = {
        service_id: serviceId,
        booking_date: bookingDate,
        booking_time: bookingTime
    };
    
    fetch('/api/bookings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(bookingData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            showNotification('Booking created successfully!', 'success');
            // If on bookings page, reload the bookings
            if (document.getElementById('user-bookings')) {
                loadUserBookings();
            }
        }
    })
    .catch(error => {
        console.error('Error creating booking:', error);
        showNotification('Failed to create booking. Please try again.', 'error');
    });
}

// Admin service functions
function createService() {
    const serviceName = document.getElementById('new-service-name').value;
    const serviceDescription = document.getElementById('new-service-description').value;
    const servicePrice = document.getElementById('new-service-price').value;
    
    if (!serviceName || !servicePrice) {
        showNotification('Name and price are required', 'error');
        return;
    }
    
    const serviceData = {
        name: serviceName,
        description: serviceDescription,
        price: parseFloat(servicePrice)
    };
    
    fetch('/api/admin/services', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(serviceData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, 'error');
        } else {
            showNotification('Service created successfully!', 'success');
            // Clear the form
            document.getElementById('new-service-name').value = '';
            document.getElementById('new-service-description').value = '';
            document.getElementById('new-service-price').value = '';
            // Reload services
            loadServices();
        }
    })
    .catch(error => {
        console.error('Error creating service:', error);
        showNotification('Failed to create service. Please try again.', 'error');
    });
}

// Provider Earnings Dashboard Functions
function loadProviderEarnings() {
    fetch('/api/provider/earnings/dashboard')
        .then(response => response.json())
        .then(data => {
            // Format currency values
            const totalEarnings = formatCurrency(data.total_earnings);
            const monthEarnings = formatCurrency(data.month_earnings);
            const pendingPayments = formatCurrency(data.pending_amount);

            // Update the dashboard with the earnings data
            document.querySelector('#total-earnings').textContent = totalEarnings;
            document.querySelector('#month-earnings').textContent = monthEarnings;
            document.querySelector('#pending-payments').textContent = pendingPayments;
        })
        .catch(error => {
            console.error('Error fetching provider earnings:', error);
        });
}

function loadPaymentHistory() {
    fetch('/api/provider/earnings')
        .then(response => response.json())
        .then(data => {
            const paymentHistoryTable = document.querySelector('#payment-history-table tbody');
            
            // Clear existing content
            if (paymentHistoryTable) {
                paymentHistoryTable.innerHTML = '';
                
                if (data.recent_payments && data.recent_payments.length > 0) {
                    // Add payment history rows
                    data.recent_payments.forEach(payment => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${payment.customer_name || 'Unknown'}</td>
                            <td>${payment.service_name || 'Service'}</td>
                            <td>${payment.PaymentDate || 'N/A'}</td>
                            <td>${formatCurrency(payment.Amount)}</td>
                            <td><span class="badge bg-success">${payment.PaymentStatus || 'Paid'}</span></td>
                        `;
                        paymentHistoryTable.appendChild(row);
                    });
                } else {
                    // No payment history found
                    const row = document.createElement('tr');
                    row.innerHTML = '<td colspan="5">No payments received yet</td>';
                    paymentHistoryTable.appendChild(row);
                }
            }
        })
        .catch(error => {
            console.error('Error fetching payment history:', error);
        });
}

// Helper function to format currency values
function formatCurrency(amount) {
    return '$' + parseFloat(amount || 0).toFixed(2);
}

// Initialize provider dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the provider dashboard page
    if (document.querySelector('#provider-dashboard')) {
        // Load earnings data
        loadProviderEarnings();
        
        // Load payment history
        loadPaymentHistory();
        
        // Set up refresh button if it exists
        const refreshButton = document.querySelector('#refresh-earnings');
        if (refreshButton) {
            refreshButton.addEventListener('click', function() {
                loadProviderEarnings();
                loadPaymentHistory();
            });
        }
    }
});

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    checkLoggedInStatus();
    
    // Check for page-specific elements and initialize functionality
    if (document.getElementById('user-bookings')) {
        loadUserBookings();
    }
    
    if (document.getElementById('payments-table-body')) {
        loadUserPayments();
    }
    
    if (document.getElementById('services-list')) {
        loadServices();
    }
    
    if (document.getElementById('service-select')) {
        loadServices();
    }
    
    if (document.getElementById('provider-reviews')) {
        // Extract provider ID from URL or data attribute
        const providerId = new URLSearchParams(window.location.search).get('provider_id') || 
                          document.getElementById('provider-reviews').dataset.providerId;
        if (providerId) {
            loadProviderReviews(providerId);
        }
    }
    
    // Initialize notification checking
    checkNotifications();
    setInterval(checkNotifications, 60000); // Check every minute
}); 