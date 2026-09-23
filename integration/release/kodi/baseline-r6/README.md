# Historical r6 release inputs

These four public-safe files are exact exports from fork commit
`2c772c64bf7dd78b7f49ac8a82640525b9921d00`. They preserve the old r6 builder and
its fixture tests after the actively maintained Home/search source advances.
They are not the current add-on and must not overwrite newer installed files.

Build/install the appropriate reviewed baseline, then use the separate
`../../library-experience/` source/update layer for current Home/search behavior.
The latter still requires its exact reviewed device cohort; a new device needs
normal private setup and independent acceptance. No account or device data is
included here.
