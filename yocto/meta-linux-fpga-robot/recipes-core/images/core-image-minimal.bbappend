# Lab-only login setup for Arty Z7 bring-up.
# ARTY_USER and ARTY_PASS_HASH are expected to be defined in build/conf/local.conf.
# Do not commit real password hashes to a public repo.

ROOTFS_POSTPROCESS_COMMAND:append = " arty_set_known_login; "

arty_set_known_login() {
    if [ -z "${ARTY_USER}" ] || [ -z "${ARTY_PASS_HASH}" ]; then
        bbfatal "ARTY_USER and ARTY_PASS_HASH must be set in local.conf"
    fi

    # Set root password.
    sed -i 's#^root:[^:]*:#root:${ARTY_PASS_HASH}:#' ${IMAGE_ROOTFS}${sysconfdir}/shadow

    # Add group if missing.
    if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/group; then
        echo '${ARTY_USER}:x:1000:' >> ${IMAGE_ROOTFS}${sysconfdir}/group
    fi

    # Add user if missing.
    if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/passwd; then
        echo '${ARTY_USER}:x:1000:1000:Arty User:/home/${ARTY_USER}:/bin/sh' >> ${IMAGE_ROOTFS}${sysconfdir}/passwd
    fi

    # Add/update user password.
    if grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/shadow; then
        sed -i 's#^${ARTY_USER}:[^:]*:#${ARTY_USER}:${ARTY_PASS_HASH}:#' ${IMAGE_ROOTFS}${sysconfdir}/shadow
    else
        echo '${ARTY_USER}:${ARTY_PASS_HASH}:19000:0:99999:7:::' >> ${IMAGE_ROOTFS}${sysconfdir}/shadow
    fi

    # Add gshadow entry if gshadow exists.
    if [ -f ${IMAGE_ROOTFS}${sysconfdir}/gshadow ]; then
        if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/gshadow; then
            echo '${ARTY_USER}:!::' >> ${IMAGE_ROOTFS}${sysconfdir}/gshadow
        fi
    fi

    # Create home directory.
    install -d -m 0755 -o 1000 -g 1000 ${IMAGE_ROOTFS}/home/${ARTY_USER}
}