# Sculpture with Wireless Responsive Audio

I am collaborating with an artist for a show, we are putting a light up sculpture into the water for the duration of the event, and having it response to audio played on the beach. For this I wanted to have a closeby microphone somewhere safe, and then sending data wirelessly out to the sculpture. This is a modification of the original sculpture which had a local microphone.

For this I am using two Feather-S2 boards. The one on the beach is acting as a wireless server and access point. This board has an i2s microphone. It calculates the loudness (adding the absolute value of samples, with some extra filtering). The board out with the sculpture is running off a battery and is polling with GET requests. Each GET request gives a loudness value, which it uses to update the brightness of the neopixels. It'll have some additional logic for running when requests fail (which is expected given the conditions).

For the server I used the basic example AP example.
